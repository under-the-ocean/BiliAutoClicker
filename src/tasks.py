import os
import json
import asyncio
from datetime import datetime
from .utils import utils
from .browser import Browser
from .server import Server

# 默认配置
DEFAULT_START_TIME = "00:29:57"
DEFAULT_CLICK_INTERVAL = 0.05
DEFAULT_CLICK_DURATION = 10.0

class Tasks:
    def __init__(self):
        self.task_configs = {}
        self.selected_tasks = []
        self.reward_result_cache = {}
        self.task_config_path = os.path.join(utils.get_exe_directory(), "task_configs.json")
        self.load_task_configs()
    
    def load_task_configs(self):
        """加载任务配置"""
        try:
            if os.path.exists(self.task_config_path):
                with open(self.task_config_path, 'r', encoding='utf-8') as f:
                    loaded_configs = json.load(f)
                for task_id, config in loaded_configs.items():
                    if 'start_time' in config:
                        try:
                            config['start_time'] = datetime.fromisoformat(config['start_time'])
                        except:
                            config['start_time'] = utils.parse_time_input(DEFAULT_START_TIME)
                    self.task_configs[task_id] = config
                return True, "任务配置加载成功"
            else:
                return False, "未找到任务配置文件"
        except Exception as e:
            return False, f"加载任务配置失败: {str(e)}"
    
    def save_task_configs(self):
        """保存任务配置"""
        try:
            serializable_configs = {}
            for task_id, config in self.task_configs.items():
                serializable_config = config.copy()
                if isinstance(config['start_time'], datetime):
                    serializable_config['start_time'] = config['start_time'].isoformat()
                serializable_configs[task_id] = serializable_config
            with open(self.task_config_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_configs, f, ensure_ascii=False, indent=4)
            return True, "任务配置保存成功"
        except Exception as e:
            return False, f"保存任务配置失败: {str(e)}"
    
    def add_task(self, task_id):
        """添加任务"""
        if task_id not in self.task_configs:
            self.task_configs[task_id] = {
                'start_time': utils.parse_time_input(DEFAULT_START_TIME),
                'interval': DEFAULT_CLICK_INTERVAL,
                'duration': DEFAULT_CLICK_DURATION
            }
            if task_id not in self.selected_tasks:
                self.selected_tasks.append(task_id)
            return True, "任务添加成功"
        else:
            return False, "任务已存在"
    
    def remove_task(self, task_id):
        """删除任务"""
        if task_id in self.task_configs:
            del self.task_configs[task_id]
        if task_id in self.selected_tasks:
            self.selected_tasks.remove(task_id)
        if task_id in self.reward_result_cache:
            del self.reward_result_cache[task_id]
        return True, "任务删除成功"
    
    def update_task(self, task_id, start_time, interval, duration):
        """更新任务配置"""
        try:
            parsed_time = utils.parse_time_input(start_time)
            self.task_configs[task_id] = {
                'start_time': parsed_time,
                'interval': float(interval),
                'duration': float(duration)
            }
            return True, "任务配置更新成功"
        except ValueError as e:
            return False, f"输入格式错误: {str(e)}"
    
    def apply_defaults(self):
        """应用默认值到所有任务"""
        for task_id in self.task_configs:
            self.task_configs[task_id] = {
                'start_time': utils.parse_time_input(DEFAULT_START_TIME),
                'interval': DEFAULT_CLICK_INTERVAL,
                'duration': DEFAULT_CLICK_DURATION
            }
        return True, "已应用默认值到所有任务"
    
    def clear_all_tasks(self):
        """清空所有任务"""
        self.task_configs.clear()
        self.selected_tasks.clear()
        self.reward_result_cache.clear()
        return True, "已清空所有任务"
    
    async def execute_tasks(self, browser_type, browser_executable_path, cookies_dir, server_url, running_flag):
        """执行所有任务"""
        try:
            # 初始化浏览器
            browser = Browser(browser_type, browser_executable_path, cookies_dir)
            playwright = await browser.setup_browser()
            context = await browser.launch_browser(playwright)
            
            # 初始化服务端通信
            server = Server(server_url)
            
            # 获取配置
            reward_base_url = "https://www.bilibili.com/blackboard/era-award-exchange.html"
            reward_claim_selector = '//*[@id="app"]/div/div[3]/section[2]/div[1]'
            max_reload_attempts = 3
            
            # 加载任务页面
            task_pages = {}
            for i, task_id in enumerate(self.selected_tasks):
                if not running_flag():
                    break
                page, success = await browser.setup_task_page(
                    context, reward_base_url, task_id, reward_claim_selector, max_reload_attempts, i * 2, running_flag
                )
                if success:
                    # 绑定API响应监控
                    await browser.monitor_api_response(page, task_id, self.reward_result_cache)
                    
                    # 提取页面信息并上传
                    page_info = await browser.extract_page_info(page, task_id)
                    if page_info:
                        server.upload_page_info(page_info)
                    
                    task_pages[task_id] = page
                else:
                    pass
            
            if not task_pages:
                return False, "所有TaskID初始化失败，无法继续"
            
            # 执行任务
            results = {}
            task_coroutines = []
            
            for task_id, config in self.task_configs.items():
                if task_id in task_pages and running_flag():
                    task_coroutines.append(
                        self.run_single_task(
                            browser, task_pages[task_id], task_id, reward_claim_selector,
                            config['start_time'], config['interval'], config['duration'], results, running_flag
                        )
                    )
            
            if task_coroutines:
                await asyncio.gather(*task_coroutines)
            
            # 确保每个任务都有结果记录
            for task_id, (success, message) in results.items():
                status = "成功" if success else "失败"
                if task_id not in self.reward_result_cache:
                    self.reward_result_cache[task_id] = {
                        "task_id": task_id,
                        "status": status,
                        "message": message,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "device_name": utils.get_windows_device_name()
                    }
            
            # 批量上传结果
            upload_success, upload_message = server.batch_upload_results(self.reward_result_cache, self.task_configs)
            
            return True, f"任务执行完成，{upload_message}"
            
        except Exception as e:
            return False, f"任务执行错误: {str(e)}"
        finally:
            if 'context' in locals():
                await context.close()
            if 'playwright' in locals():
                await playwright.stop()
    
    async def run_single_task(self, browser, page, task_id, target_selector, start_time, interval, duration, results, running_flag):
        """运行单个任务"""
        try:
            await browser.wait_for_start_time(start_time, running_flag)
            await browser.perform_task_clicks(page, task_id, target_selector, interval, duration, results, running_flag)
        except Exception as e:
            results[task_id] = (False, f"执行错误: {str(e)}")

# 全局任务管理器实例
tasks = Tasks()
