import os
import sys
import json

# 基础配置
DEFAULT_SERVER_URL = "http://ocean.run.place"
DEFAULT_COOKIES_DIR = "autowatch_cookies"
UNIFIED_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "unified_config.json")

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
                "screen_recording": {"enabled": False, "output_path": "recordings", "fps": 10},
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
                with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=4)
                self.client_config = default_config["client"]
                self.browser_config = default_config["browser"]
                self.server_config = default_config["app_config"]
                self.special_features = default_config["special_features"]
                print(f"⚠️ 统一配置不存在，已创建默认文件：{UNIFIED_CONFIG_PATH}")
        except Exception as e:
            self.client_config = default_config["client"]
            self.browser_config = default_config["browser"]
            self.server_config = default_config["app_config"]
            self.special_features = default_config["special_features"]
            print(f"❌ 统一配置加载失败：{str(e)}，使用默认配置")
    
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
