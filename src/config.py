import os
import sys
import json

# 基础配置
DEFAULT_SERVER_URL = "http://biliapi.ocean.run.place"
DEFAULT_COOKIES_DIR = "autowatch_cookies"
APP_VERSION = "1.3.0"  # 应用版本号

# 获取配置文件路径（支持PyInstaller打包）
def get_config_path():
    if getattr(sys, 'frozen', False):
        # 打包环境：配置文件和exe同目录
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "unified_config.json")
    else:
        # 开发环境：配置文件在项目根目录
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "unified_config.json")

UNIFIED_CONFIG_PATH = get_config_path()

class ConfigManager:
    def __init__(self):
        self.client_config = {}
        self.browser_config = {}
        self.server_config = {}
        self.special_features = {}
        self.load_unified_config()
    
    def get_exe_directory(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            return os.path.dirname(os.path.abspath(__file__))
    
    def load_unified_config(self):
        default_config = {
            "client": {
                "server_url": DEFAULT_SERVER_URL,
                "local_cookies_dir": DEFAULT_COOKIES_DIR
            },
            "browser": {
                "browser_type": "chromium",
                "browser_executable_path": None
            },
            "app_config": {},
            "special_features": {
                "auto_shutdown": {"enabled": True, "delay_minutes": 5}
            }
        }
        
        try:
            if os.path.exists(UNIFIED_CONFIG_PATH):
                with open(UNIFIED_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.client_config = config.get("client", default_config["client"])
                for key, val in default_config["client"].items():
                    if key not in self.client_config:
                        self.client_config[key] = val
                
                browser_config = config.get("browser", default_config["browser"])
                self.browser_config = browser_config
                
                self.server_config = config.get("app_config", default_config["app_config"])
                
                self.special_features = config.get("special_features", default_config["special_features"])
                
                print(f"✅ 统一配置加载成功")
                print(f"   客户端配置：{self.client_config}")
                print(f"   浏览器配置：{self.browser_config}")
            else:
                print(f"⚠️ 统一配置不存在，尝试从服务端获取配置...")
                # 从服务端获取配置
                server_config = self.fetch_config_from_server()
                if server_config:
                    # 使用服务端配置
                    self.client_config = server_config.get("client", default_config["client"])
                    for key, val in default_config["client"].items():
                        if key not in self.client_config:
                            self.client_config[key] = val
                    
                    self.browser_config = server_config.get("browser", default_config["browser"])
                    self.server_config = server_config.get("app_config", default_config["app_config"])
                    self.special_features = server_config.get("special_features", default_config["special_features"])
                    
                    # 保存服务端配置到本地
                    self.save_unified_config()
                    print(f"✅ 从服务端获取配置成功，并保存到本地")
                else:
                    # 使用默认配置
                    with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                        json.dump(default_config, f, ensure_ascii=False, indent=4)
                    self.client_config = default_config["client"]
                    self.browser_config = default_config["browser"]
                    self.server_config = default_config["app_config"]
                    self.special_features = default_config["special_features"]
                    print(f"⚠️ 从服务端获取配置失败，已创建默认配置文件：{UNIFIED_CONFIG_PATH}")
        except Exception as e:
            self.client_config = default_config["client"]
            self.browser_config = default_config["browser"]
            self.server_config = default_config["app_config"]
            self.special_features = default_config["special_features"]
            print(f"❌ 统一配置加载失败：{str(e)}，使用默认配置")
    
    def fetch_config_from_server(self):
        """从服务端获取配置"""
        try:
            import requests
            server_url = self.client_config.get("server_url", DEFAULT_SERVER_URL)
            # 构建完整的请求URL
            config_url = f"{server_url.rstrip('/')}/get_config"
            # 发送请求获取配置
            response = requests.get(config_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                content = data.get("content", {})
                # 构建客户端配置格式
                config = {
                    "client": {
                        "server_url": server_url,
                        "local_cookies_dir": content.get("cookies_dir", DEFAULT_COOKIES_DIR)
                    },
                    "browser": {
                        "browser_type": "chromium",
                        "browser_executable_path": None
                    },
                    "app_config": {
                        "cookies_dir": content.get("cookies_dir", DEFAULT_COOKIES_DIR),
                        "reward_base_url": content.get("reward_base_url", "https://www.bilibili.com/blackboard/era/award-exchange.html"),
                        "reward_claim_selector": content.get("reward_claim_selector", "//*[@id=\"app\"]/div/div[3]/section[2]/div[1]"),
                        "max_reload_attempts": content.get("max_reload_attempts", 3),
                        "reward_task_ids": content.get("reward_task_ids", {})
                    },
                    "special_features": content.get("special_features", {
                        "auto_shutdown": {"enabled": True, "delay_minutes": 5}
                    })
                }
                return config
            else:
                print(f"❌ 服务端返回错误：{data.get('message', '未知错误')}")
                return None
        except Exception as e:
            print(f"❌ 从服务端获取配置失败：{str(e)}")
            return None
    
    def save_unified_config(self):
        try:
            unified_config = {
                "client": self.client_config,
                "browser": self.browser_config,
                "app_config": self.server_config,
                "special_features": self.special_features
            }
            with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(unified_config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"❌ 保存统一配置失败：{str(e)}")
            return False
    
    def save_browser_config(self, browser_type, browser_executable_path):
        self.browser_config["browser_type"] = browser_type
        self.browser_config["browser_executable_path"] = browser_executable_path
        return self.save_unified_config()
    
    def save_special_features_config(self):
        return self.save_unified_config()
    
    def get_cookies_dir(self):
        local_cookies = self.client_config.get("local_cookies_dir")
        if local_cookies and os.path.isabs(local_cookies):
            return local_cookies
        elif local_cookies:
            return os.path.normpath(os.path.join(self.get_exe_directory(), local_cookies))
        
        server_cookies = self.server_config.get("cookies_dir")
        if server_cookies and os.path.isabs(server_cookies):
            return server_cookies
        elif server_cookies:
            return os.path.normpath(os.path.join(self.get_exe_directory(), server_cookies))
        
        return os.path.normpath(os.path.join(self.get_exe_directory(), DEFAULT_COOKIES_DIR))

# 全局配置管理器实例
config_manager = ConfigManager()
