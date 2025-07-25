import os
import glob
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor
import warnings
import shap
import matplotlib
matplotlib.use('Agg') # 使用非GUI后端，防止在服务器上出错
import matplotlib.pyplot as plt
import io
import base64
import json

# --- 全局设置 ---
warnings.filterwarnings('ignore')
try:
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
except Exception as e:
    print(f"无法设置中文字体，图像中的中文可能无法显示: {e}")

# --- 文件路径定义 ---
# 在容器内部，我们将反馈数据存储在/app/feedback_storage/目录下
FEEDBACK_FILE_PATH = '/app/feedback_storage/feedback_data.csv'

# --- 前端HTML代码 (新增了反馈模块) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI辅助公路工程前期估算</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f0f4f8; }
        .form-input:focus, .form-select:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2); outline: none; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
        .fade-in { animation: fadeIn 0.5s ease-out forwards; }
        .loader { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .shap-bar-positive { background-color: #ef4444; } /* red-500 */
        .shap-bar-negative { background-color: #3b82f6; } /* blue-500 */
    </style>
</head>
<body class="flex items-center justify-center min-h-screen py-10">
    <div class="w-full max-w-4xl mx-auto p-6 md:p-8">
        <div class="bg-white rounded-2xl shadow-xl overflow-hidden">
            <div class="p-8">
                <div class="text-center mb-8">
                    <h1 class="text-3xl md:text-4xl font-bold text-gray-800">AI辅助公路工程前期估算</h1>
                    <p class="text-gray-500 mt-2">输入项目关键参数，获取投资估算并查看AI决策依据。</p>
                </div>
                <form id="cost-form" class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6">
                    <!-- 表单输入项 (与之前版本相同) -->
                    <div class="md:col-span-2 font-semibold text-lg text-gray-700 border-b pb-2 mb-2">项目基本信息</div>
                    <div>
                        <label for="route_length_km" class="block text-sm font-medium text-gray-600 mb-1">路线总长度 (km)</label>
                        <input type="number" step="0.1" id="route_length_km" name="route_length_km" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="例如: 14.2" required>
                    </div>
                    <div>
                        <label for="highway_grade" class="block text-sm font-medium text-gray-600 mb-1">公路技术等级</label>
                        <select id="highway_grade" name="highway_grade" class="form-select w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" required>
                            <option value="一级">一级</option>
                            <option value="二级">二级</option>
                            <option value="三级">三级</option>
                            <option value="高速">高速</option>
                        </select>
                    </div>
                    <div>
                        <label for="project_type" class="block text-sm font-medium text-gray-600 mb-1">项目类型</label>
                        <select id="project_type" name="project_type" class="form-select w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" required>
                            <option value="新建">新建</option>
                            <option value="改扩建">改扩建</option>
                        </select>
                    </div>
                    <div class="md:col-span-2 font-semibold text-lg text-gray-700 border-b pb-2 mb-4 mt-4">成本构成与复杂性特征</div>
                    <div>
                        <label for="subgrade_cost_ratio" class="block text-sm font-medium text-gray-600 mb-1">路基工程费用占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="subgrade_cost_ratio" name="subgrade_cost_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.25" required>
                    </div>
                    <div>
                        <label for="pavement_cost_ratio" class="block text-sm font-medium text-gray-600 mb-1">路面工程费用占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="pavement_cost_ratio" name="pavement_cost_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.30" required>
                    </div>
                    <div>
                        <label for="bridge_culvert_cost_ratio" class="block text-sm font-medium text-gray-600 mb-1">桥涵工程费用占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="bridge_culvert_cost_ratio" name="bridge_culvert_cost_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.15" required>
                    </div>
                    <div>
                        <label for="traffic_eng_cost_ratio" class="block text-sm font-medium text-gray-600 mb-1">交通工程费用占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="traffic_eng_cost_ratio" name="traffic_eng_cost_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.05" required>
                    </div>
                     <div>
                        <label for="special_subgrade_ratio" class="block text-sm font-medium text-gray-600 mb-1">特殊路基处理占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="special_subgrade_ratio" name="special_subgrade_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.08" required>
                    </div>
                    <div>
                        <label for="land_acquisition_ratio" class="block text-sm font-medium text-gray-600 mb-1">征地拆迁费用占比</label>
                        <input type="number" step="0.01" min="0" max="1" id="land_acquisition_ratio" name="land_acquisition_ratio" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="0-1之间, 如: 0.12" required>
                    </div>
                    <div class="md:col-span-2">
                        <label for="pavement_cost_index" class="block text-sm font-medium text-gray-600 mb-1">路面成本指数</label>
                        <input type="number" step="0.01" min="0" id="pavement_cost_index" name="pavement_cost_index" class="form-input w-full px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" placeholder="高于1表示比标准贵, 如: 1.1" required>
                    </div>

                    <div class="md:col-span-2 mt-6">
                        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition-transform transform hover:scale-105 focus:outline-none focus:ring-4 focus:ring-blue-300">
                            立即估算
                        </button>
                    </div>
                </form>
                <div id="result-container" class="mt-8 pt-6 border-t border-gray-200" style="display: none;"></div>
                
                <!-- 新增：项目后评估反馈模块 -->
                <div id="feedback-section" class="mt-8 pt-6 border-t border-dashed border-gray-300 fade-in" style="display: none;">
                     <h3 class="text-xl font-bold text-gray-800 text-center mb-4">项目后评估 - 反馈真实造价</h3>
                     <p class="text-center text-sm text-gray-500 mb-6">感谢您帮助模型进化！请输入该项目的最终实际造价，您的数据将用于优化未来的预测。</p>
                     <form id="feedback-form">
                        <!-- 隐藏字段，用于存储本次预测的输入参数 -->
                        <input type="hidden" id="feedback-input-data" name="input_data">
                        
                        <div class="flex items-center justify-center">
                            <label for="actual_cost" class="text-sm font-medium text-gray-600 mr-2">最终实际总造价(元):</label>
                            <input type="number" step="1" id="actual_cost" name="actual_cost" class="form-input w-48 px-4 py-2 bg-gray-50 border border-gray-300 rounded-lg transition" required>
                            <button type="submit" class="ml-4 bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg transition">提交反馈</button>
                        </div>
                     </form>
                     <div id="feedback-message" class="text-center mt-4"></div>
                </div>

            </div>
        </div>
        <footer class="text-center mt-6 text-sm text-gray-500">
            <p>&copy; 2025 AI辅助公路工程估算系统 (MLOps版). All Rights Reserved.</p>
        </footer>
    </div>
    <script>
        const costForm = document.getElementById('cost-form');
        const resultContainer = document.getElementById('result-container');
        const feedbackSection = document.getElementById('feedback-section');
        const feedbackForm = document.getElementById('feedback-form');
        const feedbackInputData = document.getElementById('feedback-input-data');
        const feedbackMessage = document.getElementById('feedback-message');
        const apiUrl = window.location.origin;

        let currentInputData = {};

        costForm.addEventListener('submit', function(event) {
            event.preventDefault();
            resultContainer.style.display = 'block';
            feedbackSection.style.display = 'none'; // 每次预测前先隐藏反馈区
            resultContainer.innerHTML = `<div class="flex justify-center items-center p-8"><div class="loader"></div><p class="ml-4 text-gray-600">正在调用AI模型进行计算...</p></div>`;
            
            const formData = new FormData(event.target);
            currentInputData = {}; // 重置
            formData.forEach((value, key) => {
                currentInputData[key] = !isNaN(parseFloat(value)) && isFinite(value) ? parseFloat(value) : value;
            });
            
            fetch(`${apiUrl}/predict`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(currentInputData)
            })
            .then(response => response.ok ? response.json() : response.json().then(err => { throw new Error(err.error) }))
            .then(result => {
                if (result.error) {
                    displayError(result.error);
                } else {
                    displayFullResult(result);
                    // 成功预测后，显示反馈模块
                    feedbackInputData.value = JSON.stringify(currentInputData);
                    feedbackSection.style.display = 'block';
                    feedbackMessage.innerHTML = '';
                }
            })
            .catch(error => {
                console.error('请求失败:', error);
                displayError(`请求后端服务失败: ${error.message}。`);
            });
        });

        feedbackForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const actualCost = document.getElementById('actual_cost').value;
            const inputData = JSON.parse(feedbackInputData.value);

            const feedbackData = {
                ...inputData,
                total_cost_cny: parseFloat(actualCost)
            };
            
            feedbackMessage.innerHTML = `<p class="text-blue-600">正在提交反馈数据...</p>`;

            fetch(`${apiUrl}/feedback`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(feedbackData)
            })
            .then(response => response.json())
            .then(result => {
                if(result.success) {
                    feedbackMessage.innerHTML = `<p class="text-green-600 font-semibold">${result.message}</p>`;
                } else {
                    feedbackMessage.innerHTML = `<p class="text-red-600">提交失败: ${result.error}</p>`;
                }
            })
            .catch(error => {
                console.error('反馈提交失败:', error);
                feedbackMessage.innerHTML = `<p class="text-red-600">反馈请求失败: ${error.message}</p>`;
            });
        });

        function displayFullResult(result) {
            const costInWan = (result.estimated_cost[0] / 10000).toFixed(2);
            resultContainer.innerHTML = `
                <div class="bg-green-50 border-l-4 border-green-500 text-green-800 p-6 rounded-lg shadow-md fade-in">
                    <p class="text-lg">预测总造价:</p>
                    <p class="text-4xl font-bold mt-2">${costInWan} <span class="text-2xl font-medium">万元</span></p>
                </div>
                <div id="visualization-container" class="mt-8 fade-in">
                    <h3 class="text-xl font-bold text-gray-800 text-center mb-4">AI决策依据可视化</h3>
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <div id="force-plot-container" class="bg-gray-50 p-4 rounded-lg shadow-inner"></div>
                        <div id="summary-plot-container" class="bg-gray-50 p-4 rounded-lg shadow-inner flex flex-col items-center justify-center">
                            <button id="load-summary-btn" class="bg-white hover:bg-gray-100 text-gray-800 font-semibold py-2 px-4 border border-gray-400 rounded shadow">加载全局特征重要性图</button>
                            <div id="summary-plot-content" class="mt-4 w-full"></div>
                        </div>
                    </div>
                </div>
            `;
            displayForcePlot(result);
            document.getElementById('load-summary-btn').addEventListener('click', loadSummaryPlot);
        }
        
        function displayForcePlot(data) {
            const container = document.getElementById('force-plot-container');
            const baseValueWan = (data.base_value / 10000).toFixed(2);
            const finalValueWan = (data.estimated_cost[0] / 10000).toFixed(2);
            let contributions = data.feature_names.map((name, i) => ({
                name: name,
                value: data.feature_values[i],
                shap: data.shap_values[i]
            })).filter(c => Math.abs(c.shap) > 1e-6).sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
            const maxShap = Math.max(...contributions.map(c => Math.abs(c.shap))) || 1;
            let plotHtml = `<h4 class="font-semibold text-center mb-2">单次预测力图</h4>
                            <div class="text-xs text-center text-gray-500 mb-4">
                                基准价格: ${baseValueWan}万 &rarr; <strong class="text-blue-600">最终预测: ${finalValueWan}万</strong>
                            </div>
                            <div class="space-y-2 text-xs">`;
            contributions.forEach(c => {
                const barWidth = (Math.abs(c.shap) / maxShap) * 100;
                const isPositive = c.shap > 0;
                const barClass = isPositive ? 'shap-bar-positive' : 'shap-bar-negative';
                const featureValueDisplay = typeof c.value === 'number' ? c.value.toFixed(2) : c.value;
                plotHtml += `
                    <div class="flex items-center">
                        <div class="w-2/5 truncate pr-2 text-right" title="${c.name}=${featureValueDisplay}">${c.name} = ${featureValueDisplay}</div>
                        <div class="w-3/5">
                            <div class="${barClass} h-4 rounded-sm" style="width: ${barWidth}%;" title="影响: ${isPositive ? '+' : ''}${(c.shap/10000).toFixed(2)}万"></div>
                        </div>
                    </div>
                `;
            });
            plotHtml += `</div>`;
            container.innerHTML = plotHtml;
        }

        function loadSummaryPlot() {
            const contentDiv = document.getElementById('summary-plot-content');
            contentDiv.innerHTML = `<div class="flex justify-center items-center"><div class="loader"></div></div>`;
            fetch(`${apiUrl}/shap_summary_plot`)
            .then(response => response.ok ? response.json() : response.json().then(err => { throw new Error(err.error) }))
            .then(result => {
                if(result.image) {
                    contentDiv.innerHTML = `<img src="data:image/png;base64,${result.image}" alt="全局特征重要性图" class="w-full h-auto"/>`;
                } else {
                    contentDiv.innerText = '无法加载图像。';
                }
            })
            .catch(error => {
                console.error('加载摘要图失败:', error);
                contentDiv.innerHTML = `<p class="text-red-500">加载图像失败: ${error.message}</p>`;
            });
        }

        function displayError(message) {
            resultContainer.innerHTML = `
                <div class="bg-red-50 border-l-4 border-red-500 text-red-800 p-6 rounded-lg shadow-md fade-in">
                    <p class="font-bold">估算失败</p>
                    <p class="mt-2">${message}</p>
                </div>
            `;
        }
    </script>
</body>
</html>
"""

# --- 数据处理与模型训练逻辑 (已更新) ---
def parse_cost_data(df):
    costs = {}
    df['金额'] = df['金额'].astype(str).str.replace(',', '').astype(float)
    cost_mapping = {
        'total_cost': '公路基本造价', 'build_install_cost': '建筑安装工程费',
        'subgrade_cost': '路基工程', 'pavement_cost': '路面工程',
        'bridge_culvert_cost': '桥梁涵洞工程', 'traffic_eng_cost': '交通工程及沿线设施',
        'special_subgrade_cost': '特殊路基处理', 'land_acquisition_cost': '土地使用及拆迁补偿费'
    }
    for key, term in cost_mapping.items():
        row = df[df['项目名称'].str.contains(term, na=False)]
        costs[key] = row['金额'].iloc[0] if not row.empty else 0
    if costs['total_cost'] == 0:
        row = df[df['项目名称'].str.contains('第一至四部分合计', na=False)]
        if not row.empty: costs['total_cost'] = row['金额'].iloc[0]
    return costs

def process_single_file(filepath):
    try:
        df = pd.read_csv(filepath, encoding='utf-8')
    except:
        df = pd.read_csv(filepath, encoding='gbk')
    length_row = df[df['项目名称'].str.contains('公路公里', na=False)]
    route_length_km = float(length_row['数量'].iloc[0]) if not length_row.empty else 1.0
    costs = parse_cost_data(df)
    build_install_cost = costs['build_install_cost'] if costs['build_install_cost'] > 0 else 1
    total_cost = costs['total_cost'] if costs['total_cost'] > 0 else 1
    subgrade_cost_total = costs['subgrade_cost'] if costs['subgrade_cost'] > 0 else 1
    features = {
        'route_length_km': route_length_km,
        'subgrade_cost_ratio': costs['subgrade_cost'] / build_install_cost,
        'pavement_cost_ratio': costs['pavement_cost'] / build_install_cost,
        'bridge_culvert_cost_ratio': costs['bridge_culvert_cost'] / build_install_cost,
        'traffic_eng_cost_ratio': costs['traffic_eng_cost'] / build_install_cost,
        'special_subgrade_ratio': costs['special_subgrade_cost'] / subgrade_cost_total,
        'land_acquisition_ratio': costs['land_acquisition_cost'] / total_cost,
        'total_cost_cny': costs['total_cost']
    }
    if '一级' in filepath or '高速' in filepath: features['highway_grade'] = '一级'
    elif '三级' in filepath: features['highway_grade'] = '三级'
    else: features['highway_grade'] = '二级'
    features['project_type'] = '新建' if '新建' in filepath else '改扩建'
    pavement_area = features['route_length_km'] * 1000 * 20 
    pavement_area = pavement_area if pavement_area > 0 else 1
    actual_pavement_unit_cost = costs['pavement_cost'] / pavement_area
    standard_pavement_unit_cost = 700 
    features['pavement_cost_index'] = actual_pavement_unit_cost / standard_pavement_unit_cost
    return features

def load_and_process_all_data(data_path='data', feedback_path=FEEDBACK_FILE_PATH):
    """加载初始数据和所有反馈数据"""
    # 加载初始数据
    initial_files = glob.glob(os.path.join(data_path, '*.csv'))
    if not initial_files:
        raise FileNotFoundError(f"在 '{data_path}' 目录下未找到任何初始CSV数据文件。")
    
    initial_features = [process_single_file(f) for f in initial_files]
    df_initial = pd.DataFrame(initial_features)
    
    # 加载反馈数据
    if os.path.exists(feedback_path):
        print(f"发现反馈数据文件: {feedback_path}")
        df_feedback = pd.read_csv(feedback_path)
        # 合并新旧数据
        df_combined = pd.concat([df_initial, df_feedback], ignore_index=True)
        print(f"数据合并完成。初始数据: {len(df_initial)}条, 反馈数据: {len(df_feedback)}条, 总计: {len(df_combined)}条。")
        return df_combined
    else:
        print("未发现反馈数据文件，仅使用初始数据进行训练。")
        return df_initial

def train_model(df):
    X = df.drop('total_cost_cny', axis=1)
    y = df['total_cost_cny']
    categorical_features = ['highway_grade', 'project_type']
    numeric_features = X.select_dtypes(include=np.number).columns.tolist()
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), numeric_features),
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
        ], remainder='passthrough')
    model_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', XGBRegressor(objective='reg:squarederror', n_estimators=100, random_state=42))
    ])
    model_pipeline.fit(X, y)
    try:
        ohe_feature_names = model_pipeline.named_steps['preprocessor'].named_transformers_['cat'].get_feature_names_out(categorical_features)
        all_feature_names = numeric_features + ohe_feature_names.tolist()
    except: # 兼容旧版sklearn
        ohe_feature_names = model_pipeline.named_steps['preprocessor'].named_transformers_['cat'].get_feature_names(categorical_features)
        all_feature_names = numeric_features + list(ohe_feature_names)
        
    print("模型训练完成。")
    return model_pipeline, X.columns.tolist(), all_feature_names

# --- Flask应用设置 ---
app = Flask(__name__)
CORS(app)

# --- 应用启动时，加载数据、训练模型、创建SHAP解释器 ---
model_pipeline = None
explainer = None
TRAINING_COLS = []
ALL_FEATURE_NAMES = []
shap_values_global = None

try:
    print("正在加载数据并训练模型...")
    # 确保feedback目录存在
    os.makedirs(os.path.dirname(FEEDBACK_FILE_PATH), exist_ok=True)
    
    processed_df = load_and_process_all_data()
    model_pipeline, TRAINING_COLS, ALL_FEATURE_NAMES = train_model(processed_df)
    X_train_processed = pd.DataFrame(
        model_pipeline.named_steps['preprocessor'].transform(processed_df.drop('total_cost_cny', axis=1)),
        columns=ALL_FEATURE_NAMES
    )
    explainer = shap.Explainer(model_pipeline.named_steps['regressor'], X_train_processed)
    shap_values_global = explainer(X_train_processed)
    print("系统准备就绪。")
except Exception as e:
    print(f"初始化失败: {e}")

# --- API端点 ---
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/feedback', methods=)
def handle_feedback():
    """接收并存储用户反馈的数据"""
    try:
        data = request.get_json(force=True)
        df_new = pd.DataFrame([data])
        
        # 将新数据追加到CSV文件中
        # 如果文件不存在，则创建并写入表头；否则，追加并不写表头
        df_new.to_csv(FEEDBACK_FILE_PATH, mode='a', header=not os.path.exists(FEEDBACK_FILE_PATH), index=False)
        
        return jsonify({'success': True, 'message': '反馈成功！新数据已保存，重启应用后模型将自动学习。'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/shap_summary_plot')
def get_shap_summary_plot():
    if shap_values_global is None:
        return jsonify({'error': 'SHAP值未计算，无法生成图像。'}), 500
    try:
        fig, ax = plt.subplots(figsize=(10, 8))
        shap.summary_plot(shap_values_global, plot_type="bar", show=False, feature_names=ALL_FEATURE_NAMES)
        plt.title('全局特征重要性')
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        return jsonify({'image': img_str})
    except Exception as e:
        return jsonify({'error': f'生成图像时出错: {str(e)}'}), 500

@app.route('/predict', methods=)
def predict():
    if model_pipeline is None or explainer is None:
        return jsonify({'error': '模型或解释器未成功加载。'}), 500
    try:
        data = request.get_json(force=True)
        input_df = pd.DataFrame([data], columns=TRAINING_COLS)
        input_processed = pd.DataFrame(
            model_pipeline.named_steps['preprocessor'].transform(input_df),
            columns=ALL_FEATURE_NAMES
        )
        prediction = model_pipeline.predict(input_df)
        shap_values_single = explainer(input_processed)
        return jsonify({
            'estimated_cost': prediction.tolist(),
            'shap_values': shap_values_single.values[0].tolist(),
            'base_value': shap_values_single.base_values[0],
            'feature_names': ALL_FEATURE_NAMES,
            'feature_values': input_processed.iloc[0].tolist()
        })
    except Exception as e:
        return jsonify({'error': f'预测时发生错误: {str(e)}'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)