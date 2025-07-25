# 步骤1: 使用阿里云官方仓库的、包含完整路径的操作系统镜像作为基础
# 这个精确地址确保了构建服务能从阿里云内部直接获取镜像，100%绕开所有外部网络和权限问题
FROM registry.cn-hangzhou.aliyuncs.com/alinux/alinux:3

# 步骤2: 在这个基础系统上，安装Python和pip
# 使用yum作为包管理器，这是Alibaba Cloud Linux的标配
RUN yum update -y && \
    yum install -y python3 python3-pip && \
    yum clean all

# 步骤3: 创建一个软链接，让系统默认的python命令指向python3
RUN ln -s /usr/bin/python3 /usr/bin/python

# --- 后续步骤与之前相同 ---

# 步骤4: 在容器内创建一个工作目录
WORKDIR /app

# 步骤5: 复制依赖文件并安装依赖库
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 步骤6: 将我们应用的所有文件复制到容器的工作目录中
COPY . .

# 步骤7: 暴露容器的端口
EXPOSE 5000

# 步骤8: 定义容器启动时要执行的命令
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
