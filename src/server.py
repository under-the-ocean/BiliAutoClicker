import requests
import json
import os
from datetime import datetime
from .utils import utils
from .logger import logger

# API配置
TARGET_API_PATH = "/x/activity_components/mission/receive"
UPLOAD_ENDPOINT_SUFFIX = "/upload_reward_result"
UPLOAD_PAGE_INFO_SUFFIX = "/upload_page_info"
RETRY_COUNT = 2

class Server:
    def __init__(self, server_url):
        self.server_url = server_url
        self.upload_endpoint = f"{server_url.rstrip('/')}{UPLOAD_ENDPOINT_SUFFIX}"
        self.upload_page_info_endpoint = f"{server_url.rstrip('/')}{UPLOAD_PAGE_INFO_SUFFIX}"
    
    def fetch_server_config(self):
        """从服务端拉取配置"""
        server_api = f"{self.server_url.rstrip('/')}/get_config"
        
        try:
            headers = {"Device-ID": utils.get_device_id()}
            response = requests.get(server_api, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                server_config = data.get("content", {})
                server_task_ids = server_config.get("reward_task_ids", {})
                return True, server_config, server_task_ids
            else:
                return False, {}, {}, f"服务端返回错误：{data.get('msg', '未知错误')}"
        except requests.exceptions.RequestException as e:
            return False, {}, {}, f"服务端请求失败：{str(e)}"
        except json.JSONDecodeError:
            return False, {}, {}, "服务端返回格式错误"
    
    def batch_upload_results(self, reward_result_cache, task_configs):
        """批量上传所有任务结果"""
        if not reward_result_cache and not task_configs:
            return False, "没有需要上传的结果数据"
            
        # 补全未捕获结果的任务
        for task_id in task_configs.keys():
            if task_id not in reward_result_cache:
                reward_result_cache[task_id] = {
                    "task_id": task_id,
                    "status": "未执行",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device_name": utils.get_windows_device_name()
                }
        
        # 构建上传数据
        upload_data = {
            "device_name": utils.get_windows_device_name(),
            "total_tasks": len(reward_result_cache),
            "results": list(reward_result_cache.values()),
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 带重试的上传逻辑
        for retry in range(RETRY_COUNT + 1):
            try:
                headers = {"Content-Type": "application/json"}
                response = requests.post(
                    self.upload_endpoint,
                    data=json.dumps(upload_data, ensure_ascii=False),
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()
                
                # 上传日志文件
                log_success, log_message = logger.upload_log_file(self.server_url)
                
                return True, f"批量上传成功，共{len(reward_result_cache)}条结果"
            except Exception as e:
                if retry < RETRY_COUNT:
                    continue
                else:
                    # 保存本地备份
                    self.save_local_backup(upload_data)
                    return False, f"所有重试均失败：{str(e)}"
    
    def upload_page_info(self, page_info_data):
        """上传页面信息到服务器"""
        try:
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                self.upload_page_info_endpoint,
                data=json.dumps(page_info_data, ensure_ascii=False),
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            return False
    
    def save_local_backup(self, data):
        """本地备份上传失败的数据"""
        backup_dir = os.path.join(utils.get_exe_directory(), "upload_backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, 
                                  f"backup_{utils.get_windows_device_name()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            return False
