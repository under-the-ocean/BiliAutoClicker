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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行任务...")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 浏览器类型: {browser_type}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 浏览器路径: {browser_executable_path or '默认路径'}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Cookie目录: {cookies_dir}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 服务端地址: {server_url}")
            
            # 初始化浏览器
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 初始化浏览器...")
            browser = Browser(browser_type, browser_executable_path, cookies_dir)
            playwright = await browser.setup_browser()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Playwright初始化成功")
            context = await browser.launch_browser(playwright)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 浏览器启动成功")
            
            # 初始化服务端通信
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 初始化服务端通信...")
            server = Server(server_url)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 服务端通信初始化成功")
            
            # 从配置文件获取配置
            from .config import config_manager
            reward_base_url = config_manager.server_config.get("reward_base_url", "https://www.bilibili.com/blackboard/era-award-exchange.html")
            reward_claim_selector = config_manager.server_config.get("reward_claim_selector", '//*[@id="app"]/div/div[3]/section[2]/div[1]')
            max_reload_attempts = config_manager.server_config.get("context_retry_count", 3)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 配置信息: 基础URL={reward_base_url}, 选择器={reward_claim_selector}, 最大重试次数={max_reload_attempts}")
            
            # 加载任务页面
            task_pages = {}
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始加载任务页面，共{len(self.selected_tasks)}个任务")
            for i, task_id in enumerate(self.selected_tasks):
                if not running_flag():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务执行被用户终止")
                    break
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 加载任务 {i+1}/{len(self.selected_tasks)}: {task_id}")
                page, success = await browser.setup_task_page(
                    context, reward_base_url, task_id, reward_claim_selector, max_reload_attempts, i * 2, running_flag
                )
                if success:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 任务页面加载成功: {task_id}")
                    # 绑定API响应监控
                    await browser.monitor_api_response(page, task_id, self.reward_result_cache)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ API响应监控已绑定: {task_id}")
                    
                    # 提取页面信息并上传
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 提取页面信息: {task_id}")
                    page_info = await browser.extract_page_info(page, task_id)
                    if page_info:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 页面信息提取成功，正在上传...")
                        upload_success = server.upload_page_info(page_info)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 页面信息上传: {'成功' if upload_success else '失败'}")
                    
                    task_pages[task_id] = page
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 任务页面加载失败: {task_id}")
            
            if not task_pages:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 所有TaskID初始化失败，无法继续")
                return False, "所有TaskID初始化失败，无法继续"
            
            # 执行任务
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行任务，共{len(task_pages)}个任务页面")
            results = {}
            task_coroutines = []
            
            for task_id, config in self.task_configs.items():
                if task_id in task_pages and running_flag():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 准备执行任务: {task_id}, 开始时间: {config['start_time'].strftime('%H:%M:%S')}, 间隔: {config['interval']}s, 持续时间: {config['duration']}s")
                    task_coroutines.append(
                        self.run_single_task(
                            browser, task_pages[task_id], task_id, reward_claim_selector,
                            config['start_time'], config['interval'], config['duration'], results, running_flag
                        )
                    )
            
            if task_coroutines:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始并发执行{len(task_coroutines)}个任务")
                await asyncio.gather(*task_coroutines)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 所有任务执行完成")
            
            # 确保每个任务都有结果记录
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 整理任务执行结果...")
            for task_id, (success, message) in results.items():
                status = "成功" if success else "失败"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: {status} - {message}")
                if task_id not in self.reward_result_cache:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 为任务 {task_id} 创建结果记录")
                    self.reward_result_cache[task_id] = {
                        "task_id": task_id,
                        "status": status,
                        "message": message,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "device_name": utils.get_windows_device_name()
                    }
            
            # 批量上传结果
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 批量上传任务结果，共{len(self.reward_result_cache)}个结果")
            upload_success, upload_message = server.batch_upload_results(self.reward_result_cache, self.task_configs)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 结果上传: {'成功' if upload_success else '失败'} - {upload_message}")
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务执行完成")
            return True, f"任务执行完成，{upload_message}"
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 任务执行错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, f"任务执行错误: {str(e)}"
        finally:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 清理资源...")
            if 'context' in locals():
                try:
                    await context.close()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 浏览器上下文已关闭")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 关闭浏览器上下文失败: {str(e)}")
            if 'playwright' in locals():
                try:
                    await playwright.stop()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Playwright已停止")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 停止Playwright失败: {str(e)}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 资源清理完成")
    
    async def run_single_task(self, browser, page, task_id, target_selector, start_time, interval, duration, results, running_flag):
        """运行单个任务"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行任务: {task_id}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待开始时间: {start_time.strftime('%H:%M:%S')}")
            
            # 计算等待时间
            current_time = datetime.now()
            wait_time = (start_time - current_time).total_seconds()
            if wait_time > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 需要等待: {wait_time:.2f}秒")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始时间已过，立即执行")
            
            await browser.wait_for_start_time(start_time, running_flag)
            
            if not running_flag():
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id} 被用户终止")
                results[task_id] = (False, "任务被用户终止")
                return
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行点击任务: {task_id}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 点击参数: 选择器={target_selector}, 间隔={interval}s, 持续时间={duration}s")
            
            await browser.perform_task_clicks(page, task_id, target_selector, interval, duration, results, running_flag)
            
            if task_id in results:
                success, message = results[task_id]
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id} 执行完成: {'成功' if success else '失败'} - {message}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id} 执行完成，但未收到结果")
                results[task_id] = (False, "未收到执行结果")
        except Exception as e:
            error_message = f"执行错误: {str(e)}"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 任务 {task_id} 执行出错: {error_message}")
            import traceback
            traceback.print_exc()
            results[task_id] = (False, error_message)

# 全局任务管理器实例
tasks = Tasks()
