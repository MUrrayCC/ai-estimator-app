# 步骤1: 使用Docker官方中国区镜像作为基础
# 这是最后的尝试，旨在绕开阿里云内部仓库的权限问题
FROM registry.docker-cn.com/library/python:3.9-slim

# 步骤2: 在容器内创建一个工作目录
WORKDIR /app

# 步骤3: 复制依赖文件并安装依赖库
COPY requirements.txt .
# 继续使用阿里云的pip源来加速库的下载
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 步骤4: 将我们应用的所有文件复制到容器的工作目录中
COPY . .

# 步骤5: 暴露容器的端口
EXPOSE 5000

# 步骤6: 定义容器启动时要执行的命令
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
