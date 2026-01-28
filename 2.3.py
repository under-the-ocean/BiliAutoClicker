import asyncio
import time
import json
import os
import sys
import threading
import subprocess
import requests
from datetime import datetime, timedelta
import customtkinter as ctk
from tkinter import scrolledtext, messagebox, END, filedialog
from playwright.async_api import async_playwright, TimeoutError

# 基础配置
DEFAULT_SERVER_URL = "http://ocean.run.place"
DEFAULT_COOKIES_DIR = "autowatch_cookies"
UNIFIED_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "unified_config.json")

# 批量上传相关配置
TARGET_API_PATH = "/x/activity_components/mission/receive"
UPLOAD_ENDPOINT_SUFFIX = "/upload_reward_result"
UPLOAD_PAGE_INFO_SUFFIX = "/upload_page_info"  # 新增：上传页面信息的接口
RETRY_COUNT = 2

# 新增：本地日志文件配置
LOG_FILE_NAME = "api_responses.log"
LOG_DIR = "logs"

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

def set_custom_fonts():
    default_font = ("SDK_SC_WEB", 12)
    ctk.CTkFont.default_font = default_font
    ctk.set_widget_scaling(1.1)
    return {
        "default": ctk.CTkFont(family="SDK_SC_WEB", size=12),
        "small": ctk.CTkFont(family="SDK_SC_WEB", size=10),
        "medium": ctk.CTkFont(family="SDK_SC_WEB", size=14),
        "large": ctk.CTkFont(family="SDK_SC_WEB", size=16, weight="bold"),
        "monospace": ctk.CTkFont(family="SDK_SC_WEB", size=11)
    }

print("作者：ocean之下")
print("作者主页：https://space.bilibili.com/3546571704634103")
print(f"服务端地址：{DEFAULT_SERVER_URL}（可通过client_config.json修改）")
print("使用前需用autowatch登录！")

DEFAULT_START_TIME = "00:29:57"
DEFAULT_CLICK_INTERVAL = 0.05
DEFAULT_CLICK_DURATION = 10.0

class AutoClickerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("B站自动点击器（服务端同步版）- by ocean之下")
        self.root.geometry("1000x800")
        self.root.resizable(True, True)
        
        self.custom_fonts = set_custom_fonts()
        
        # 核心配置变量 - 先初始化基础属性
        self.log_text = None  # 先声明log_text属性
        
        self.client_config = {}
        self.server_config = {}
        self.server_task_ids = {}
        self.selected_tasks = []
        self.task_configs = {}
        self.task_checkboxes = {}
        self.task_vars = {}
        self.running = False
        
        # 添加浏览器类型配置
        self.browser_type = "chromium"  # 默认为chromium
        self.browser_executable_path = None  # 浏览器可执行文件路径
        self.supported_browsers = ["firefox", "chromium", "webkit", "chrome", "msedge"]  # 支持的浏览器类型
        
        # 批量上传相关变量
        self.reward_result_cache = {}
        self.windows_device_name = self.get_windows_device_name()
        self.upload_endpoint = ""
        self.upload_page_info_endpoint = ""  # 新增：上传页面信息的端点
        
        # 事件循环管理
        self.loop = None
        self.loop_thread = None
        self.async_thread = None  # 新增：专门运行异步任务的线程
        
        # 初始化顺序调整：解决循环依赖
        self.load_unified_config()  # 1. 加载统一配置
        self.log_file_path = self.setup_log_file(skip_log=True)  # 2. 先初始化路径，不记录日志
        self.create_widgets()  # 3. 创建UI组件，此时可使用log_file_path
        self.log(f"API响应日志文件路径：{self.log_file_path}")  # 4. 现在补全日志记录
        self.fetch_server_config()
        self.load_task_configs()
        
        # 初始化上传地址
        self.upload_endpoint = f"{self.client_config['server_url'].rstrip('/')}{UPLOAD_ENDPOINT_SUFFIX}"
        self.upload_page_info_endpoint = f"{self.client_config['server_url'].rstrip('/')}{UPLOAD_PAGE_INFO_SUFFIX}"  # 新增
        self.log(f"已初始化上传地址：{self.upload_endpoint}，设备名：{self.windows_device_name}")
        self.log(f"页面信息上传地址：{self.upload_page_info_endpoint}")  # 新增
        
        self.center_window()

    def setup_log_file(self, skip_log=False):  # 这里添加skip_log参数并设置默认值
        """设置日志文件路径并确保目录存在，增加skip_log参数控制是否记录日志"""
        exe_dir = self.get_exe_directory()
        log_dir = os.path.join(exe_dir, LOG_DIR)
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, LOG_FILE_NAME)
        
        # 只有当skip_log为False且log_text已初始化时才记录日志
        if not skip_log and self.log_text is not None:
            self.log(f"API响应日志文件路径：{log_file_path}")
            
        return log_file_path

    def save_api_response_to_log(self, task_id, response_data):
        """将API响应保存到本地日志文件"""
        try:
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "task_id": task_id,
                "device_name": self.windows_device_name,
                "response": response_data
            }
            
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            self.log(f"❌ 保存API响应到日志文件失败：{str(e)}")

    def upload_log_file(self):
        """上传日志文件到服务器"""
        if not os.path.exists(self.log_file_path):
            self.log("⚠️ 没有找到日志文件，无需上传")
            return False
            
        try:
            with open(self.log_file_path, 'rb') as f:
                files = {'log_file': (os.path.basename(self.log_file_path), f, 'application/json')}
                data = {
                    'device_name': self.windows_device_name,
                    'upload_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                response = requests.post(
                    f"{self.client_config['server_url'].rstrip('/')}/upload_log_file",
                    files=files,
                    data=data,
                    timeout=30
                )
                response.raise_for_status()
                
            self.log(f"✅ 日志文件上传成功：{os.path.basename(self.log_file_path)}")
            return True
            
        except Exception as e:
            self.log(f"❌ 日志文件上传失败：{str(e)}")
            return False

    async def extract_page_info(self, page, task_id):
        """提取页面信息并上传到服务器"""
        try:
            # 等待页面加载完成
            await page.wait_for_load_state('networkidle')
            
            # 提取第一个元素文本
            element1 = await page.query_selector('//*[@id="app"]/div/div[3]/section[1]/p[1]')
            text1 = await element1.text_content() if element1 else "未找到元素1"
            
            # 提取第二个元素文本
            element2 = await page.query_selector('//*[@id="app"]/div/div[3]/section[1]/p[2]')
            text2 = await element2.text_content() if element2 else "未找到元素2"
            
            # 构建上传数据
            page_info_data = {
                "task_id": task_id,
                "device_name": self.windows_device_name,
                "section_title": text1.strip() if text1 else "",
                "award_info": text2.strip() if text2 else "",
                "extract_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 上传到服务器
            success = await self.upload_page_info(page_info_data)
            if success:
                self.log(f"✅ 页面信息上传成功 - TaskID: {task_id}")
                self.log(f"   标题: {page_info_data['section_title']}")
                self.log(f"   奖励信息: {page_info_data['award_info']}")
            else:
                self.log(f"❌ 页面信息上传失败 - TaskID: {task_id}")
                
            return page_info_data
            
        except Exception as e:
            self.log(f"❌ 提取页面信息失败 - TaskID {task_id}: {str(e)}")
            return None

    async def upload_page_info(self, page_info_data):
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
            self.log(f"❌ 上传页面信息到服务器失败：{str(e)}")
            return False

    def get_windows_device_name(self):
        """获取Windows系统的设备名称（计算机名）"""
        try:
            if sys.platform.startswith('win32'):
                return os.environ.get('COMPUTERNAME', f"windows_device_{os.getpid()}")
            else:
                import socket
                return socket.gethostname()
        except Exception as e:
            return f"unknown_device_{str(e)[:8]}"

    def batch_upload_results(self):
        """批量上传所有任务结果，使用Windows设备名作为标识"""
        if not self.reward_result_cache:
            self.log("没有需要上传的结果数据")
            return False
            
        # 补全未捕获结果的任务
        for task_id in self.task_configs.keys():
            if task_id not in self.reward_result_cache:
                self.reward_result_cache[task_id] = {
                    "task_id": task_id,
                    "status": "未执行",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device_name": self.windows_device_name
                }
        
        # 构建上传数据
        upload_data = {
            "device_name": self.windows_device_name,
            "total_tasks": len(self.reward_result_cache),
            "results": list(self.reward_result_cache.values()),
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
                self.log(f"✅ 批量上传成功（设备：{self.windows_device_name}），共{len(self.reward_result_cache)}条结果")
                
                # 新增：上传日志文件
                self.log("开始上传API响应日志文件...")
                log_upload_success = self.upload_log_file()
                if log_upload_success:
                    self.log("✅ API响应日志文件上传完成")
                else:
                    self.log("❌ API响应日志文件上传失败")
                    
                return True
            except Exception as e:
                if retry < RETRY_COUNT:
                    self.log(f"❌ 第{retry+1}次上传失败：{str(e)}，将重试")
                    time.sleep(2)
                else:
                    self.log(f"❌ 所有重试均失败：{str(e)}")
                    self.save_local_backup(upload_data)
                    return False

    def save_local_backup(self, data):
        """本地备份上传失败的数据"""
        backup_dir = os.path.join(os.path.dirname(sys.argv[0]), "upload_backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, 
                                  f"backup_{self.windows_device_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log(f"⚠️ 结果已保存本地备份：{backup_path}")
        except Exception as e:
            self.log(f"❌ 本地备份失败：{str(e)}")

    async def monitor_api_response(self, page, task_id):
        """监控API响应并缓存结果，同时保存到本地日志"""
        def handle_response(response):
            if TARGET_API_PATH in response.url and response.request.method == "POST":
                try:
                    async def process_response():
                        try:
                            resp_json = await response.json()
                            response_data = {
                                "task_id": task_id,
                                "status": "成功" if resp_json.get("code") == 0 else "失败",
                                "response_code": resp_json.get("code"),
                                "message": resp_json.get("message", ""),
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "device_name": self.windows_device_name,
                                "url": response.url,
                                "status_code": response.status
                            }
                            
                            # 缓存结果
                            self.reward_result_cache[task_id] = response_data
                            
                            # 新增：保存到本地日志文件
                            self.save_api_response_to_log(task_id, response_data)
                            
                            self.log(f"[Task {task_id}] 捕获API响应，状态：{response_data['status']}")
                        except Exception as e:
                            self.log(f"[Task {task_id}] 解析响应失败：{str(e)}")
                    
                    asyncio.create_task(process_response())
                except Exception as e:
                    self.log(f"[Task {task_id}] 处理响应时出错：{str(e)}")
        
        page.on("response", handle_response)

    def get_exe_directory(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def load_unified_config(self):
        """加载统一配置文件"""
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
                
                # 加载客户端配置
                self.client_config = config.get("client", default_config["client"])
                for key, val in default_config["client"].items():
                    if key not in self.client_config:
                        self.client_config[key] = val
                
                # 加载浏览器配置
                browser_config = config.get("browser", default_config["browser"])
                self.browser_type = browser_config.get("browser_type", default_config["browser"]["browser_type"])
                self.browser_executable_path = browser_config.get("browser_executable_path", default_config["browser"]["browser_executable_path"])
                
                # 加载应用配置
                self.server_config = config.get("app_config", default_config["app_config"])
                
                # 加载特殊功能配置
                self.special_features = config.get("special_features", default_config["special_features"])
                
                print(f"✅ 统一配置加载成功")
                print(f"   客户端配置：{self.client_config}")
                print(f"   浏览器配置：{self.browser_type}, 路径：{self.browser_executable_path}")
            else:
                with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=4)
                self.client_config = default_config["client"]
                self.browser_type = default_config["browser"]["browser_type"]
                self.browser_executable_path = default_config["browser"]["browser_executable_path"]
                self.server_config = default_config["app_config"]
                self.special_features = default_config["special_features"]
                print(f"⚠️ 统一配置不存在，已创建默认文件：{UNIFIED_CONFIG_PATH}")
        except Exception as e:
            self.client_config = default_config["client"]
            self.browser_type = default_config["browser"]["browser_type"]
            self.browser_executable_path = default_config["browser"]["browser_executable_path"]
            self.server_config = default_config["app_config"]
            self.special_features = default_config["special_features"]
            print(f"❌ 统一配置加载失败：{str(e)}，使用默认配置")

    def fetch_server_config(self):
        self.log("正在从服务端拉取配置...")
        server_api = f"{self.client_config['server_url'].rstrip('/')}/get_config"
        
        try:
            headers = {"Device-ID": self.get_device_id()}
            response = requests.get(server_api, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                self.server_config = data.get("content", {})
                self.server_task_ids = self.server_config.get("reward_task_ids", {})
                self.log(f"✅ 服务端配置拉取成功，获取{len(self.server_task_ids)}个TaskID")
                for key, val in self.server_task_ids.items():
                    self.log(f"  - {key}: {val}")
            else:
                self.server_config = {}
                self.server_task_ids = {}
                self.log(f"❌ 服务端返回错误：{data.get('msg', '未知错误')}")
        except requests.exceptions.RequestException as e:
            self.server_config = {}
            self.server_task_ids = {}
            self.log(f"❌ 服务端请求失败：{str(e)}")
            self.log("⚠️ 降级使用本地默认TaskID列表")
            self.server_task_ids = {
                "1": "18ERA1wloghwww000",
                "2": "18ERA1wloghwz800",
                "3": "18ERA1wloghwf700"
            }
        except json.JSONDecodeError:
            self.server_config = {}
            self.server_task_ids = {}
            self.log(f"❌ 服务端返回格式错误，降级使用本地默认TaskID")
            self.server_task_ids = {
                "1": "18ERA1wloghwww000",
                "2": "18ERA1wloghwz800",
                "3": "18ERA1wloghwf700"
            }
        
        self.update_task_list()

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

    def get_device_id(self):
        import hashlib
        system_info = f"{sys.platform}-{os.name}-{os.getlogin()}"
        return hashlib.md5(system_info.encode()).hexdigest()[:16]

    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

    def create_widgets(self):
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 20))
        
        title_label = ctk.CTkLabel(title_frame, text="B站自动点击器（服务端同步版）", font=self.custom_fonts["large"])
        title_label.pack(anchor="w")
        
        device_label = ctk.CTkLabel(title_frame, 
                                  text=f"当前设备：{self.windows_device_name} | 上传地址：{self.upload_endpoint}",
                                  font=self.custom_fonts["small"])
        device_label.pack(anchor="w", pady=(5, 0))
        
        server_label = ctk.CTkLabel(title_frame, 
                                  text=f"当前服务端：{self.client_config['server_url']} | Cookie路径：{self.get_cookies_dir()}",
                                  font=self.custom_fonts["small"])
        server_label.pack(anchor="w", pady=(5, 0))
        
        # 浏览器选择控件
        browser_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        browser_frame.pack(anchor="w", pady=(5, 0))
        
        ctk.CTkLabel(browser_frame, text="浏览器选择:", font=self.custom_fonts["small"]).pack(side="left")
        
        self.browser_var = ctk.StringVar(value=self.browser_type)
        browser_dropdown = ctk.CTkComboBox(
            browser_frame,
            values=self.supported_browsers,
            variable=self.browser_var,
            width=100,
            font=self.custom_fonts["small"],
            command=self.change_browser
        )
        browser_dropdown.pack(side="left", padx=(5, 0))
        
        # 浏览器路径选择控件
        browser_path_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        browser_path_frame.pack(anchor="w", pady=(5, 0))
        
        ctk.CTkLabel(browser_path_frame, text="浏览器路径:", font=self.custom_fonts["small"]).pack(side="left")
        
        self.browser_path_var = ctk.StringVar(value=self.browser_executable_path or "")
        browser_path_entry = ctk.CTkEntry(
            browser_path_frame,
            textvariable=self.browser_path_var,
            width=300,
            font=self.custom_fonts["small"]
        )
        browser_path_entry.pack(side="left", padx=(5, 5))
        
        select_path_btn = ctk.CTkButton(
            browser_path_frame,
            text="浏览",
            command=self.select_browser_path,
            width=60,
            font=self.custom_fonts["small"]
        )
        select_path_btn.pack(side="left", padx=(0, 5))
        
        save_path_btn = ctk.CTkButton(
            browser_path_frame,
            text="保存",
            command=self.save_browser_config,
            width=60,
            font=self.custom_fonts["small"]
        )
        save_path_btn.pack(side="left")
        
        # 新增：日志文件信息显示
        log_info_label = ctk.CTkLabel(title_frame, 
                                    text=f"API日志文件：{os.path.basename(self.log_file_path)}",
                                    font=self.custom_fonts["small"])
        log_info_label.pack(anchor="w", pady=(5, 0))
        
        author_label = ctk.CTkLabel(title_frame, 
                                  text="作者: ocean之下 | 主页: https://space.bilibili.com/3546571704634103",
                                  font=self.custom_fonts["small"])
        author_label.pack(anchor="w", pady=(5, 0))
        
        paned_window = ctk.CTkFrame(main_frame)
        paned_window.pack(fill="both", expand=True)
        
        left_frame = ctk.CTkFrame(paned_window, width=350)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        task_frame = ctk.CTkFrame(left_frame, corner_radius=8)
        task_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        ctk.CTkLabel(task_frame, text="服务端TaskID列表（自动同步）", font=self.custom_fonts["medium"]).pack(anchor="w", pady=(10, 5), padx=10)
        
        refresh_btn = ctk.CTkButton(task_frame, text="刷新服务端TaskID", command=self.refresh_server_config, font=self.custom_fonts["small"])
        refresh_btn.pack(anchor="w", padx=10, pady=(0, 5))
        
        listbox_container = ctk.CTkFrame(task_frame)
        listbox_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.scrollable_frame = ctk.CTkScrollableFrame(listbox_container)
        self.scrollable_frame.pack(fill="both", expand=True)
        
        self.update_task_list()
        
        add_selected_btn = ctk.CTkButton(task_frame, text="添加选中TaskID", command=self.add_selected_tasks, font=self.custom_fonts["default"])
        add_selected_btn.pack(fill="x", padx=10, pady=(0, 15))
        
        ctk.CTkLabel(task_frame, text="手动输入TaskID（补充）", font=self.custom_fonts["default"]).pack(anchor="w", padx=10, pady=(0, 5))
        
        input_frame = ctk.CTkFrame(task_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.manual_task_var = ctk.StringVar()
        task_entry = ctk.CTkEntry(input_frame, textvariable=self.manual_task_var, placeholder_text="输入额外TaskID", font=self.custom_fonts["default"])
        task_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        add_manual_btn = ctk.CTkButton(input_frame, text="添加", command=self.add_manual_task, width=60, font=self.custom_fonts["default"])
        add_manual_btn.pack(side="right")
        
        right_frame = ctk.CTkFrame(paned_window)
        right_frame.pack(side="right", fill="both", expand=True)
        
        config_frame = ctk.CTkFrame(right_frame, corner_radius=8)
        config_frame.pack(fill="both", pady=(0, 10))
        
        ctk.CTkLabel(config_frame, text="任务配置", font=self.custom_fonts["medium"]).pack(anchor="w", pady=(10, 5), padx=10)
        
        table_container = ctk.CTkFrame(config_frame)
        table_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.config_text = ctk.CTkTextbox(table_container, height=120, font=self.custom_fonts["monospace"])
        self.config_text.pack(fill="both", expand=True)
        self.config_text.configure(state="disabled")
        
        button_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        ctk.CTkButton(button_frame, text="编辑选中", command=self.edit_selected_task, width=80, font=self.custom_fonts["default"]).pack(side="left", padx=(0, 5))
        ctk.CTkButton(button_frame, text="删除选中", command=self.remove_selected_task, width=80, font=self.custom_fonts["default"]).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="应用默认值", command=self.apply_defaults, width=90, font=self.custom_fonts["default"]).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="清空所有", command=self.clear_all_tasks, width=80, font=self.custom_fonts["default"]).pack(side="left", padx=5)
        
        log_frame = ctk.CTkFrame(right_frame, corner_radius=8)
        log_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(log_frame, text="操作日志", font=self.custom_fonts["medium"]).pack(anchor="w", pady=(10, 5), padx=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, width=60, height=15,
                                                font=self.custom_fonts["monospace"],
                                                bg="#2b2b2b", fg="#ffffff",
                                                relief="flat", border=1)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        control_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        control_frame.pack(fill="x", pady=(10, 0))
        
        self.start_button = ctk.CTkButton(control_frame, text="开始任务", command=self.start_tasks, font=self.custom_fonts["default"])
        self.start_button.pack(side="left", padx=(0, 10))
        
        self.stop_button = ctk.CTkButton(control_frame, text="停止任务", command=self.stop_tasks, state="disabled", font=self.custom_fonts["default"])
        self.stop_button.pack(side="left", padx=10)
        
        self.upload_button = ctk.CTkButton(control_frame, text="手动上传结果", command=self.trigger_batch_upload, font=self.custom_fonts["default"])
        self.upload_button.pack(side="left", padx=10)
        
        # 新增：上传日志文件按钮
        upload_log_btn = ctk.CTkButton(control_frame, text="上传日志文件", command=self.trigger_log_upload, font=self.custom_fonts["default"])
        upload_log_btn.pack(side="left", padx=10)
        
        ctk.CTkButton(control_frame, text="保存配置", command=self.save_task_configs, font=self.custom_fonts["default"]).pack(side="left", padx=10)
        ctk.CTkButton(control_frame, text="特殊功能", command=self.open_special_features, font=self.custom_fonts["default"]).pack(side="left", padx=10)
        ctk.CTkButton(control_frame, text="清空日志", command=self.clear_log, font=self.custom_fonts["default"]).pack(side="left", padx=10)
        ctk.CTkButton(control_frame, text="退出", command=self.root.quit, font=self.custom_fonts["default"]).pack(side="left", padx=10)

    def trigger_log_upload(self):
        """触发日志文件上传"""
        threading.Thread(target=self.upload_log_file, daemon=True).start()

    def trigger_batch_upload(self):
        if not self.reward_result_cache and not self.task_configs:
            messagebox.showinfo("提示", "没有任务结果可上传")
            return
        threading.Thread(target=self.batch_upload_results, daemon=True).start()

    def refresh_server_config(self):
        self.log("正在手动刷新服务端配置...")
        self.fetch_server_config()
        self.update_task_list()
        self.log("服务端配置刷新完成！")

    def update_task_list(self):
        if not hasattr(self, 'server_task_ids'):
            self.server_task_ids = {}
            
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.task_checkboxes.clear()
        self.task_vars.clear()
        
        if self.server_task_ids:
            for task_key, task_value in self.server_task_ids.items():
                var = ctk.BooleanVar()
                checkbox = ctk.CTkCheckBox(
                    self.scrollable_frame,
                    text=f"{task_key}. {task_value}",
                    variable=var,
                    font=self.custom_fonts["default"],
                    command=lambda k=task_key, v=var: self.on_checkbox_change(k, v)
                )
                checkbox.pack(anchor="w", pady=2, padx=5)
                self.task_checkboxes[task_key] = checkbox
                self.task_vars[task_key] = var
        else:
            tip_label = ctk.CTkLabel(self.scrollable_frame, text="暂无服务端TaskID数据", font=self.custom_fonts["small"], text_color="#666")
            tip_label.pack(anchor="w", pady=5, padx=5)

    def on_checkbox_change(self, task_key, var):
        task_value = self.server_task_ids.get(task_key, "")
        if task_value:
            if var.get() and task_value not in self.selected_tasks:
                self.selected_tasks.append(task_value)
            elif not var.get() and task_value in self.selected_tasks:
                self.selected_tasks.remove(task_value)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        # 使用线程安全的方式更新GUI
        def update_log():
            self.log_text.insert("end", f"[{timestamp}] {message}\n")
            self.log_text.see("end")
            self.root.update_idletasks()
        
        # 确保在主线程中执行GUI更新
        if threading.current_thread() == threading.main_thread():
            update_log()
        else:
            self.root.after(0, update_log)

    def add_selected_tasks(self):
        added_count = 0
        for task_key, var in self.task_vars.items():
            if var.get():
                task_value = self.server_task_ids.get(task_key, "")
                if task_value and task_value not in self.task_configs:
                    self.add_task_to_config(task_value)
                    added_count += 1
        if added_count > 0:
            self.log(f"已添加 {added_count} 个服务端TaskID到配置")
            self.update_config_display()
        else:
            messagebox.showinfo("提示", "请先勾选服务端TaskID")

    def add_manual_task(self):
        task_id = self.manual_task_var.get().strip()
        if task_id:
            if task_id not in self.task_configs:
                self.add_task_to_config(task_id)
                self.manual_task_var.set("")
                self.log(f"已添加手动TaskID: {task_id}")
                self.update_config_display()
            else:
                self.log("TaskID已存在")
        else:
            messagebox.showwarning("警告", "请输入TaskID")

    def add_task_to_config(self, task_id):
        if task_id not in self.task_configs:
            self.task_configs[task_id] = {
                'start_time': self.parse_time_input(DEFAULT_START_TIME),
                'interval': DEFAULT_CLICK_INTERVAL,
                'duration': DEFAULT_CLICK_DURATION
            }
            if task_id not in self.selected_tasks:
                self.selected_tasks.append(task_id)

    def parse_time_input(self, time_str):
        time_str = time_str.strip()
        if not time_str:
            return self.parse_time_input(DEFAULT_START_TIME)
        if time_str.startswith('+'):
            try:
                seconds = float(time_str[1:])
                return datetime.now() + timedelta(seconds=seconds)
            except ValueError:
                raise ValueError(f"无效的相对时间格式: {time_str}")
        try:
            time_part = datetime.strptime(time_str, "%H:%M:%S").time()
            today = datetime.now().date()
            target_time = datetime.combine(today, time_part)
            if target_time < datetime.now():
                target_time += timedelta(days=1)
            return target_time
        except ValueError:
            try:
                seconds = float(time_str)
                return datetime.now() + timedelta(seconds=seconds)
            except ValueError:
                raise ValueError(f"无效的时间格式: {time_str}")

    def update_config_display(self):
        def update_display():
            self.config_text.configure(state="normal")
            self.config_text.delete("1.0", "end")
            if self.task_configs:
                header = f"{'TaskID':<30}{'开始时间':<15}{'点击间隔':<10}{'持续时间':<10}\n"
                self.config_text.insert("end", header)
                self.config_text.insert("end", "-" * 65 + "\n")
                for task_id, config in self.task_configs.items():
                    start_time_str = config['start_time'].strftime("%H:%M:%S") if isinstance(config['start_time'], datetime) else str(config['start_time'])
                    row = f"{task_id:<30}{start_time_str:<15}{config['interval']:<10.2f}{config['duration']:<10.1f}\n"
                    self.config_text.insert("end", row)
            else:
                self.config_text.insert("end", "暂无任务配置")
            self.config_text.configure(state="disabled")
        
        # 确保在主线程中更新
        if threading.current_thread() == threading.main_thread():
            update_display()
        else:
            self.root.after(0, update_display)

    def save_task_configs(self):
        if not self.task_configs:
            messagebox.showinfo("提示", "没有可保存的任务配置")
            return
        try:
            exe_dir = self.get_exe_directory()
            task_config_path = os.path.normpath(os.path.join(exe_dir, "task_configs.json"))
            serializable_configs = {}
            for task_id, config in self.task_configs.items():
                serializable_config = config.copy()
                if isinstance(config['start_time'], datetime):
                    serializable_config['start_time'] = config['start_time'].isoformat()
                serializable_configs[task_id] = serializable_config
            with open(task_config_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_configs, f, ensure_ascii=False, indent=4)
            self.log("✅ 任务配置保存成功")
            messagebox.showinfo("成功", "任务配置已保存")
        except Exception as e:
            self.log(f"❌ 保存任务配置失败: {str(e)}")
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")

    def load_task_configs(self):
        try:
            exe_dir = self.get_exe_directory()
            task_config_path = os.path.normpath(os.path.join(exe_dir, "task_configs.json"))
            if os.path.exists(task_config_path):
                with open(task_config_path, 'r', encoding='utf-8') as f:
                    loaded_configs = json.load(f)
                for task_id, config in loaded_configs.items():
                    if 'start_time' in config:
                        try:
                            config['start_time'] = datetime.fromisoformat(config['start_time'])
                        except:
                            config['start_time'] = self.parse_time_input(DEFAULT_START_TIME)
                    self.task_configs[task_id] = config
                self.log("✅ 任务配置加载成功")
                self.update_config_display()
            else:
                self.log("⚠️ 未找到任务配置文件")
        except Exception as e:
            self.log(f"❌ 加载任务配置失败: {str(e)}")

    def save_special_features_config(self):
        """保存特殊功能配置到统一配置文件"""
        try:
            # 读取现有配置
            unified_config = {}
            if os.path.exists(UNIFIED_CONFIG_PATH):
                with open(UNIFIED_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    unified_config = json.load(f)
            
            # 更新特殊功能配置
            unified_config["special_features"] = self.special_features
            
            with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(unified_config, f, ensure_ascii=False, indent=4)
            
            self.log("✅ 特殊功能配置保存成功")
            return True
        except Exception as e:
            self.log(f"❌ 保存特殊功能配置失败: {str(e)}")
            return False

    def load_special_features_config(self):
        """特殊功能配置已在load_unified_config中加载，此方法保留以兼容"""
        pass

    def edit_selected_task(self):
        if not self.task_configs:
            messagebox.showwarning("警告", "请先添加任务")
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("编辑任务配置")
        dialog.geometry("500x600")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_container = ctk.CTkFrame(dialog)
        main_container.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main_container, text="编辑任务配置", font=self.custom_fonts["large"]).pack(pady=(0, 15))
        
        scrollable_container = ctk.CTkScrollableFrame(main_container, height=380)
        scrollable_container.pack(fill="both", expand=True)
        
        form_frame = ctk.CTkFrame(scrollable_container, fg_color="transparent")
        form_frame.pack(fill="x", padx=5)
        
        ctk.CTkLabel(form_frame, text="选择TaskID:", font=self.custom_fonts["default"]).grid(row=0, column=0, sticky="w", pady=8)
        task_var = ctk.StringVar(value=list(self.task_configs.keys())[0])
        task_combo = ctk.CTkComboBox(form_frame, values=list(self.task_configs.keys()), variable=task_var, font=self.custom_fonts["default"])
        task_combo.grid(row=0, column=1, sticky="ew", pady=8, padx=(10, 0))
        
        current_config = self.task_configs[task_var.get()]
        start_time_str = current_config['start_time'].strftime("%H:%M:%S") if isinstance(current_config['start_time'], datetime) else str(current_config['start_time'])
        
        ctk.CTkLabel(form_frame, text="开始时间:", font=self.custom_fonts["default"]).grid(row=1, column=0, sticky="w", pady=8)
        start_var = ctk.StringVar(value=start_time_str)
        start_entry = ctk.CTkEntry(form_frame, textvariable=start_var, font=self.custom_fonts["default"])
        start_entry.grid(row=1, column=1, sticky="ew", pady=8, padx=(10, 0))
        
        ctk.CTkLabel(form_frame, text="点击间隔(秒):", font=self.custom_fonts["default"]).grid(row=2, column=0, sticky="w", pady=8)
        interval_var = ctk.StringVar(value=str(current_config['interval']))
        interval_entry = ctk.CTkEntry(form_frame, textvariable=interval_var, font=self.custom_fonts["default"])
        interval_entry.grid(row=2, column=1, sticky="ew", pady=8, padx=(10, 0))
        
        ctk.CTkLabel(form_frame, text="持续时间(秒):", font=self.custom_fonts["default"]).grid(row=3, column=0, sticky="w", pady=8)
        duration_var = ctk.StringVar(value=str(current_config['duration']))
        duration_entry = ctk.CTkEntry(form_frame, textvariable=duration_var, font=self.custom_fonts["default"])
        duration_entry.grid(row=3, column=1, sticky="ew", pady=8, padx=(10, 0))
        
        ctk.CTkLabel(form_frame, text="开始时间格式: HH:MM:SS 或 +秒数", font=self.custom_fonts["small"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 5))
        
        form_frame.columnconfigure(1, weight=1)
        
        preview_frame = ctk.CTkFrame(scrollable_container, fg_color="transparent")
        preview_frame.pack(fill="x", padx=5, pady=(15, 10))
        
        ctk.CTkLabel(preview_frame, text="配置预览:", font=self.custom_fonts["default"]).pack(anchor="w")
        
        preview_text = ctk.CTkTextbox(preview_frame, height=80, font=self.custom_fonts["monospace"])
        preview_text.pack(fill="x", pady=(5, 0))
        preview_text.insert("1.0", f"TaskID: {task_var.get()}\n")
        preview_text.insert("end", f"开始时间: {start_var.get()}\n")
        preview_text.insert("end", f"点击间隔: {interval_var.get()}秒\n")
        preview_text.insert("end", f"持续时间: {duration_var.get()}秒")
        preview_text.configure(state="disabled")
        
        def update_preview():
            preview_text.configure(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", f"TaskID: {task_var.get()}\n")
            preview_text.insert("end", f"开始时间: {start_var.get()}\n")
            preview_text.insert("end", f"点击间隔: {interval_var.get()}秒\n")
            preview_text.insert("end", f"持续时间: {duration_var.get()}秒")
            preview_text.configure(state="disabled")
        
        task_var.trace("w", lambda *args: update_preview())
        start_var.trace("w", lambda *args: update_preview())
        interval_var.trace("w", lambda *args: update_preview())
        duration_var.trace("w", lambda *args: update_preview())
        
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(15, 0))
        
        buttons = ctk.CTkFrame(button_frame, fg_color="transparent")
        buttons.pack(side="right", padx=5, pady=5)
        
        def save_changes():
            try:
                task_id = task_var.get()
                new_start = start_var.get()
                new_interval = float(interval_var.get())
                new_duration = float(duration_var.get())
                parsed_time = self.parse_time_input(new_start)
                self.task_configs[task_id] = {
                    'start_time': parsed_time,
                    'interval': new_interval,
                    'duration': new_duration
                }
                dialog.destroy()
                self.log(f"已更新TaskID {task_id} 的配置")
                self.update_config_display()
            except ValueError as e:
                messagebox.showerror("错误", f"输入格式错误: {str(e)}")
        
        def confirm_changes():
            if messagebox.askyesno("确认", "确定要保存这些更改吗？"):
                save_changes()
        
        ctk.CTkButton(buttons, text="确认", command=confirm_changes, width=80, font=self.custom_fonts["default"]).pack(side="left", padx=5)
        ctk.CTkButton(buttons, text="取消", command=dialog.destroy, width=80, font=self.custom_fonts["default"]).pack(side="left", padx=5)
        
        update_preview()

    def remove_selected_task(self):
        if not self.task_configs:
            messagebox.showwarning("警告", "没有可删除的任务")
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("删除任务")
        dialog.geometry("300x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main_frame, text="选择要删除的TaskID:", font=self.custom_fonts["medium"]).pack(pady=(0, 15))
        
        task_var = ctk.StringVar(value=list(self.task_configs.keys())[0])
        task_combo = ctk.CTkComboBox(main_frame, values=list(self.task_configs.keys()), variable=task_var, font=self.custom_fonts["default"])
        task_combo.pack(pady=10, fill="x")
        
        ctk.CTkLabel(main_frame, text="删除后无法恢复，确定要删除吗？", font=self.custom_fonts["small"], text_color="red").pack(pady=(10, 5))
        
        def delete_task():
            task_id = task_var.get()
            if task_id in self.task_configs:
                del self.task_configs[task_id]
            if task_id in self.selected_tasks:
                self.selected_tasks.remove(task_id)
            if task_id in self.reward_result_cache:
                del self.reward_result_cache[task_id]
            for task_key, task_value in self.server_task_ids.items():
                if task_value == task_id and task_key in self.task_vars:
                    self.task_vars[task_key].set(False)
            dialog.destroy()
            self.log(f"已删除TaskID: {task_id}")
            self.update_config_display()
        
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=5)
        
        ctk.CTkButton(button_frame, text="删除", command=delete_task, font=self.custom_fonts["default"]).pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(button_frame, text="取消", command=dialog.destroy, font=self.custom_fonts["default"]).pack(side="left", padx=5, fill="x", expand=True)

    def apply_defaults(self):
        for task_id in self.task_configs:
            self.task_configs[task_id] = {
                'start_time': self.parse_time_input(DEFAULT_START_TIME),
                'interval': DEFAULT_CLICK_INTERVAL,
                'duration': DEFAULT_CLICK_DURATION
            }
        self.log("已应用默认值到所有任务")
        self.update_config_display()

    def clear_all_tasks(self):
        if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
            self.task_configs.clear()
            self.selected_tasks.clear()
            self.reward_result_cache.clear()
            for var in self.task_vars.values():
                var.set(False)
            self.log("已清空所有任务")
            self.update_config_display()

    def clear_log(self):
        self.log_text.delete("1.0", "end")
        self.log("日志已清空")

    def schedule_shutdown(self, delay_minutes):
        try:
            delay_seconds = delay_minutes * 60
            if sys.platform.startswith('win'):
                subprocess.run(f"shutdown /s /t {delay_seconds}", shell=True, check=True)
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                subprocess.run(f"shutdown -h +{delay_minutes}", shell=True, check=True)
            else:
                self.log(f"不支持的操作系统: {sys.platform}")
                return False
            self.log(f"已安排在 {delay_minutes} 分钟后自动关机")
            return True
        except Exception as e:
            self.log(f"安排自动关机失败: {str(e)}")
            return False

    def cancel_shutdown(self):
        try:
            if sys.platform.startswith('win'):
                subprocess.run("shutdown /a", shell=True, check=True)
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                subprocess.run("shutdown -c", shell=True, check=True)
            else:
                self.log(f"不支持的操作系统: {sys.platform}")
                return False
            self.log("已取消自动关机")
            return True
        except Exception as e:
            self.log(f"取消自动关机失败: {str(e)}")
            return False

    def open_special_features(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("特殊功能")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main_frame, text="特殊功能设置", font=self.custom_fonts["large"]).pack(pady=(0, 15))
        
        shutdown_frame = ctk.CTkFrame(main_frame)
        shutdown_frame.pack(fill="x", padx=5, pady=5)
        
        self.shutdown_enabled_var = ctk.BooleanVar(value=self.special_features["auto_shutdown"]["enabled"])
        ctk.CTkCheckBox(
            shutdown_frame,
            text="任务完成后自动关机",
            variable=self.shutdown_enabled_var,
            font=self.custom_fonts["default"]
        ).pack(anchor="w", pady=(8, 3))
        
        delay_frame = ctk.CTkFrame(shutdown_frame, fg_color="transparent")
        delay_frame.pack(fill="x", pady=(8, 3))
        
        ctk.CTkLabel(
            delay_frame,
            text="关机延迟时间:",
            font=self.custom_fonts["default"],
            width=100
        ).pack(side="left", padx=(0, 8))
        
        self.shutdown_delay_var = ctk.StringVar(value=str(self.special_features["auto_shutdown"]["delay_minutes"]))
        ctk.CTkEntry(
            delay_frame,
            textvariable=self.shutdown_delay_var,
            width=70,
            font=self.custom_fonts["default"]
        ).pack(side="left")
        
        ctk.CTkLabel(
            delay_frame,
            text="分钟 (任务完成后等待时间)",
            font=self.custom_fonts["small"]
        ).pack(side="left", padx=(8, 0))
        
        cancel_shutdown_btn = ctk.CTkButton(
            shutdown_frame,
            text="取消已设置的关机",
            command=self.cancel_shutdown,
            font=self.custom_fonts["small"],
            width=120,
            height=25
        )
        cancel_shutdown_btn.pack(anchor="w", pady=(10, 5), padx=5)
        
        ctk.CTkLabel(
            shutdown_frame,
            text="注意: 启用后任务完成将自动关机，请保存工作",
            font=self.custom_fonts["small"],
            text_color="red",
            wraplength=350
        ).pack(anchor="w", pady=(5, 5))
        
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        
        def save_special_settings():
            try:
                self.special_features["auto_shutdown"]["enabled"] = self.shutdown_enabled_var.get()
                self.special_features["auto_shutdown"]["delay_minutes"] = int(self.shutdown_delay_var.get())
                if self.save_special_features_config():
                    messagebox.showinfo("成功", "特殊功能配置已保存")
                    dialog.destroy()
            except ValueError as e:
                messagebox.showerror("输入错误", f"请输入有效的数值: {str(e)}")
        
        ctk.CTkButton(
            button_frame,
            text="保存设置",
            command=save_special_settings,
            font=self.custom_fonts["default"],
            width=80
        ).pack(side="right", padx=(0, 8))
        
        ctk.CTkButton(
            button_frame,
            text="取消",
            command=dialog.destroy,
            font=self.custom_fonts["default"],
            width=80
        ).pack(side="right")

    def start_tasks(self):
        if not self.task_configs:
            messagebox.showwarning("警告", "请先添加任务")
            return
        # 清空之前的结果缓存
        self.reward_result_cache.clear()
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        
        # 修复：在单独的线程中运行异步任务，避免阻塞GUI
        self.async_thread = threading.Thread(target=self.run_async_tasks, daemon=True)
        self.async_thread.start()

    def stop_tasks(self):
        self.running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.log("正在停止任务...")

    def change_browser(self, event=None):
        """改变浏览器类型"""
        self.browser_type = self.browser_var.get()
        self.log(f"浏览器已切换为: {self.browser_type}")
    
    def select_browser_path(self):
        """选择浏览器可执行文件路径"""
        file_path = filedialog.askopenfilename(
            title="选择浏览器可执行文件",
            filetypes=[
                ("可执行文件", "*.exe"),
                ("应用程序", "*.app"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.browser_path_var.set(file_path)
            self.browser_executable_path = file_path
            self.log(f"已选择浏览器路径: {file_path}")
    
    def save_browser_config(self):
        """保存浏览器配置到统一配置文件"""
        try:
            self.browser_type = self.browser_var.get()
            self.browser_executable_path = self.browser_path_var.get()
            
            # 读取现有配置
            unified_config = {}
            if os.path.exists(UNIFIED_CONFIG_PATH):
                with open(UNIFIED_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    unified_config = json.load(f)
            
            # 更新浏览器配置
            unified_config["browser"] = {
                "browser_type": self.browser_type,
                "browser_executable_path": self.browser_executable_path
            }
            
            with open(UNIFIED_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(unified_config, f, ensure_ascii=False, indent=4)
            
            self.log("✅ 浏览器配置已保存")
            messagebox.showinfo("成功", "浏览器配置已保存")
        except Exception as e:
            self.log(f"❌ 保存浏览器配置失败: {str(e)}")
            messagebox.showerror("错误", f"保存浏览器配置失败: {str(e)}")

    def run_async_tasks(self):
        """在单独的线程中运行异步任务，避免阻塞GUI主线程"""
        try:
            # 创建新的事件循环
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # 为Windows设置正确的事件循环策略
            if sys.platform.startswith('win'):
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            # 运行主异步函数
            self.loop.run_until_complete(self.main_async())
            
            # 任务完成后执行批量上传
            self.log("\n=== 所有任务执行完毕，开始批量上传结果 ===")
            self.batch_upload_results()
            
        except Exception as e:
            self.log(f"任务执行错误: {str(e)}")
        finally:
            # 清理资源
            self.running = False
            if self.special_features["auto_shutdown"]["enabled"]:
                self.schedule_shutdown(self.special_features["auto_shutdown"]["delay_minutes"])
            
            # 在主线程中更新GUI状态
            def update_gui():
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
            
            self.root.after(0, update_gui)
            
            # 关闭事件循环
            if self.loop and not self.loop.is_closed():
                self.loop.close()

    async def main_async(self):
        cookies_dir = self.get_cookies_dir()
        reward_base_url = self.server_config.get("reward_base_url", "https://www.bilibili.com/blackboard/era-award-exchange.html")
        reward_claim_selector = self.server_config.get("reward_claim_selector", '//*[@id="app"]/div/div[3]/section[2]/div[1]')
        max_reload_attempts = self.server_config.get("max_reload_attempts", 3)
        
        self.log(f"使用Cookie路径: {cookies_dir}")
        self.log(f"抢码基础URL: {reward_base_url}")
        self.log(f"当前浏览器类型: {self.browser_type}")
        if self.browser_executable_path:
            self.log(f"浏览器路径: {self.browser_executable_path}")
        
        async with async_playwright() as p:
            # 根据选择的浏览器类型启动相应的浏览器
            launch_options = {
                "user_data_dir": cookies_dir,
                "headless": False,
                "args": ["--disable-background-timer-throttling"]
            }
            
            # 如果指定了浏览器路径，则添加executable_path选项
            if self.browser_executable_path:
                launch_options["executable_path"] = self.browser_executable_path
            
            if self.browser_type == "firefox":
                context = await p.firefox.launch_persistent_context(**launch_options)
            elif self.browser_type == "chromium":
                context = await p.chromium.launch_persistent_context(**launch_options)
            elif self.browser_type == "webkit":
                context = await p.webkit.launch_persistent_context(**launch_options)
            elif self.browser_type == "chrome":
                # 对于Chrome，我们使用chromium的API，但指定Chrome的路径
                context = await p.chromium.launch_persistent_context(**launch_options)
            elif self.browser_type == "msedge":
                # 对于Edge，我们使用chromium的API，但指定Edge的路径
                if not self.browser_executable_path:
                    launch_options["channel"] = "msedge"
                context = await p.chromium.launch_persistent_context(**launch_options)
            else:
                # 默认使用chromium
                context = await p.chromium.launch_persistent_context(**launch_options)
            try:
                task_pages = {}
                self.log(f"正在初始化 {len(self.selected_tasks)} 个TaskID页面...")
                
                for i, task_id in enumerate(self.selected_tasks):
                    if not self.running:
                        self.log("任务已停止")
                        return
                    self.log(f"正在加载TaskID {i+1}/{len(self.selected_tasks)}: {task_id}")
                    page, success = await self.setup_task_page(
                        context, reward_base_url, task_id, reward_claim_selector, max_reload_attempts, i * 2
                    )
                    if success:
                        # 绑定API响应监控
                        await self.monitor_api_response(page, task_id)
                        
                        # 新增：提取页面信息并上传
                        self.log(f"正在提取TaskID {task_id} 的页面信息...")
                        page_info = await self.extract_page_info(page, task_id)
                        
                        task_pages[task_id] = page
                        self.log(f"TaskID {task_id} 加载成功")
                    else:
                        self.log(f"TaskID {task_id} 加载失败")
                
                if not task_pages:
                    self.log("所有TaskID初始化失败，无法继续")
                    return
                
                self.log(f"成功初始化 {len(task_pages)} 个TaskID页面")
                results = {}
                task_coroutines = []
                
                for task_id, config in self.task_configs.items():
                    if task_id in task_pages and self.running:
                        task_coroutines.append(
                            self.run_single_task(
                                task_pages[task_id], task_id, reward_claim_selector,
                                config['start_time'], config['interval'], config['duration'], results
                            )
                        )
                
                if task_coroutines:
                    await asyncio.gather(*task_coroutines)
                
                self.log("任务执行结果:")
                for task_id, (success, message) in results.items():
                    status = "成功" if success else "失败"
                    self.log(f"TaskID {task_id}: {status} - {message}")
                    
                    # 确保每个任务都有结果记录
                    if task_id not in self.reward_result_cache:
                        self.reward_result_cache[task_id] = {
                            "task_id": task_id,
                            "status": status,
                            "message": message,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "device_name": self.windows_device_name
                        }
            except Exception as e:
                self.log(f"操作错误：{str(e)}")
            finally:
                await context.close()

    async def setup_task_page(self, context, base_url, task_id, selector, max_attempts, delay_before_load=0):
        if delay_before_load > 0:
            await asyncio.sleep(delay_before_load)
        page = None
        try:
            for attempt in range(1, max_attempts + 1):
                if not self.running:
                    return None, False
                if page:
                    await page.close()
                page = await context.new_page()
                await page.set_viewport_size({"width": 480, "height": 640})
                target_url = f"{base_url}?task_id={task_id}"
                await page.goto(target_url)
                await page.wait_for_load_state("networkidle", timeout=30000)
                try:
                    await page.wait_for_selector(selector, timeout=15000)
                    activation_result = await page.evaluate('''(selector) => {
                        const btn = document.evaluate(selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!btn) return {success: false, message: '未找到按钮'};
                        btn.removeAttribute('disabled');
                        btn.classList.remove('disabled', 'disable');
                        btn.classList.add('active');
                        btn.style.pointerEvents = 'auto';
                        btn.style.opacity = '1';
                        btn.textContent = '关注ocean之下';
                        return {success: true, message: '按钮已激活并修改文本'};
                    }''', selector)
                    if activation_result['success']:
                        return page, True
                except TimeoutError:
                    pass
                except Exception:
                    pass
                if attempt < max_attempts and self.running:
                    await asyncio.sleep(2)
            if page:
                await page.close()
            return None, False
        except Exception:
            if page:
                await page.close()
            return None, False

    async def run_single_task(self, page, task_id, target_selector, start_time, interval, duration, results):
        try:
            await self.wait_for_start_time(start_time)
            await self.perform_task_clicks(page, task_id, target_selector, interval, duration, results)
        except Exception as e:
            self.log(f"TaskID {task_id} 执行错误: {str(e)}")
            results[task_id] = (False, f"执行错误: {str(e)}")

    async def wait_for_start_time(self, start_time):
        while datetime.now() < start_time and self.running:
            remaining = (start_time - datetime.now()).total_seconds()
            if int(remaining) % 10 == 0 and remaining > 0:
                self.log(f"TaskID 等待中，剩余 {int(remaining)} 秒")
            await asyncio.sleep(0.1)

    async def perform_task_clicks(self, page, task_id, target_selector, interval, duration, results):
        click_count = 0
        success_count = 0
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time and self.running:
            try:
                await page.click(target_selector, timeout=50)
                success_count += 1
            except Exception:
                pass
            click_count += 1
            if interval > 0 and self.running:
                await asyncio.sleep(interval)
        result = f"{duration}秒点击结束，共点击 {click_count} 次，成功 {success_count} 次"
        results[task_id] = (True, result)

def main():
    if hasattr(ctk, "set_widget_scaling"):
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
    root = ctk.CTk()
    app = AutoClickerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()