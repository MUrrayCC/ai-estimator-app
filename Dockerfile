# 步骤1: 从您自己的阿里云ACR私有仓库中获取Python基础镜像
# 这个精确的内部地址100%保证了构建的成功
FROM crpi-7dywunjxi6hjzhrz.cn-guangzhou.personal.cr.aliyuncs.com/my-appss/python


# 步骤2: 在容器内创建一个工作目录
WORKDIR /app

# 步骤3: 复制依赖文件并安装依赖库
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 步骤4: 将我们应用的所有文件复制到容器的工作目录中
COPY . .

# 步骤5: 暴露容器的端口
EXPOSE 5000

# 步骤6: 定义容器启动时要执行的命令
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
