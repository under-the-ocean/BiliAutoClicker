import os
import json
from datetime import datetime
from .utils import utils

# 日志配置
LOG_FILE_NAME = "api_responses.log"
LOG_DIR = "logs"

class Logger:
    def __init__(self):
        self.log_file_path = self.setup_log_file()
    
    def setup_log_file(self, skip_log=False):
        """设置日志文件路径并确保目录存在"""
        exe_dir = utils.get_exe_directory()
        log_dir = os.path.join(exe_dir, LOG_DIR)
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, LOG_FILE_NAME)
        return log_file_path
    
    def save_api_response_to_log(self, task_id, response_data):
        """将API响应保存到本地日志文件"""
        try:
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "task_id": task_id,
                "device_name": utils.get_windows_device_name(),
                "response": response_data
            }
            
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            print(f"❌ 保存API响应到日志文件失败：{str(e)}")
    
    def upload_log_file(self, server_url):
        """上传日志文件到服务器"""
        if not os.path.exists(self.log_file_path):
            return False, "没有找到日志文件，无需上传"
            
        try:
            import requests
            with open(self.log_file_path, 'rb') as f:
                files = {'log_file': (os.path.basename(self.log_file_path), f, 'application/json')}
                data = {
                    'device_name': utils.get_windows_device_name(),
                    'upload_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                response = requests.post(
                    f"{server_url.rstrip('/')}/upload_log_file",
                    files=files,
                    data=data,
                    timeout=30
                )
                response.raise_for_status()
                
            return True, f"日志文件上传成功：{os.path.basename(self.log_file_path)}"
            
        except Exception as e:
            return False, f"日志文件上传失败：{str(e)}"
    
    def get_log_file_path(self):
        """获取日志文件路径"""
        return self.log_file_path

# 全局日志管理器实例
logger = Logger()
