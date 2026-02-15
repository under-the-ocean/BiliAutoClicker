import asyncio
import time
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError
from .server import TARGET_API_PATH
from .logger import logger

class Browser:
    def __init__(self, browser_type, browser_executable_path, cookies_dir):
        self.browser_type = browser_type
        self.browser_executable_path = browser_executable_path
        self.cookies_dir = cookies_dir
    
    async def setup_browser(self):
        """设置浏览器"""
        playwright = await async_playwright().start()
        return playwright
    
    async def launch_browser(self, playwright):
        """启动浏览器"""
        launch_options = {
            "user_data_dir": self.cookies_dir,
            "headless": False,
            "args": ["--disable-background-timer-throttling"]
        }
        
        # 如果指定了浏览器路径，则添加executable_path选项
        if self.browser_executable_path:
            launch_options["executable_path"] = self.browser_executable_path
        
        if self.browser_type == "firefox":
            context = await playwright.firefox.launch_persistent_context(**launch_options)
        elif self.browser_type == "chromium":
            context = await playwright.chromium.launch_persistent_context(**launch_options)
        elif self.browser_type == "webkit":
            context = await playwright.webkit.launch_persistent_context(**launch_options)
        elif self.browser_type == "chrome":
            # 对于Chrome，我们使用chromium的API，但指定Chrome的路径
            context = await playwright.chromium.launch_persistent_context(**launch_options)
        elif self.browser_type == "msedge":
            # 对于Edge，我们使用chromium的API，但指定Edge的路径
            if not self.browser_executable_path:
                launch_options["channel"] = "msedge"
            context = await playwright.chromium.launch_persistent_context(**launch_options)
        else:
            # 默认使用chromium
            context = await playwright.chromium.launch_persistent_context(**launch_options)
        
        return context
    
    async def setup_task_page(self, context, base_url, task_id, selector, max_attempts, delay_before_load=0, running_flag=None):
        """设置任务页面"""
        if delay_before_load > 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 等待 {delay_before_load} 秒后加载页面")
            await asyncio.sleep(delay_before_load)
        page = None
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 开始加载页面，最大重试次数: {max_attempts}")
            for attempt in range(1, max_attempts + 1):
                if running_flag and not running_flag():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 加载被用户终止")
                    return None, False
                
                if page:
                    await page.close()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 关闭之前的页面")
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 第 {attempt}/{max_attempts} 次尝试加载页面")
                page = await context.new_page()
                await page.set_viewport_size({"width": 480, "height": 640})
                target_url = f"{base_url}?task_id={task_id}"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 访问URL: {target_url}")
                
                try:
                    await page.goto(target_url)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 页面导航成功")
                    
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 页面加载完成")
                    
                    try:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 等待选择器出现: {selector}")
                        await page.wait_for_selector(selector, timeout=15000)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 选择器找到")
                        
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 激活按钮并修改文本")
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
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ✅ 页面设置成功")
                            return page, True
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 按钮激活失败: {activation_result['message']}")
                    except TimeoutError:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 选择器超时")
                    except Exception as e:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 页面操作失败: {str(e)}")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 页面导航失败: {str(e)}")
                
                if attempt < max_attempts and (not running_flag or running_flag()):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 等待 2 秒后重试")
                    await asyncio.sleep(2)
            
            if page:
                await page.close()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 关闭页面")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 所有尝试均失败")
            return None, False
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: ❌ 加载页面时发生错误: {str(e)}")
            if page:
                await page.close()
            return None, False
    
    async def monitor_api_response(self, page, task_id, reward_result_cache):
        """监控API响应并缓存结果"""
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
                                "device_name": self.get_device_name(),
                                "url": response.url,
                                "status_code": response.status
                            }
                            
                            # 缓存结果
                            reward_result_cache[task_id] = response_data
                            
                            # 保存到本地日志文件
                            logger.save_api_response_to_log(task_id, response_data)
                            
                        except Exception as e:
                            pass
                    
                    asyncio.create_task(process_response())
                except Exception as e:
                    pass
        
        page.on("response", handle_response)
    
    async def extract_page_info(self, page, task_id):
        """提取页面信息"""
        try:
            # 等待页面加载完成
            await page.wait_for_load_state('networkidle')
            
            # 提取第一个元素文本
            element1 = await page.query_selector('//*[@id="app"]/div/div[3]/section[1]/p[1]')
            text1 = await element1.text_content() if element1 else "未找到元素1"
            
            # 提取第二个元素文本
            element2 = await page.query_selector('//*[@id="app"]/div/div[3]/section[1]/p[2]')
            text2 = await element2.text_content() if element2 else "未找到元素2"
            
            # 构建页面信息
            page_info_data = {
                "task_id": task_id,
                "device_name": self.get_device_name(),
                "section_title": text1.strip() if text1 else "",
                "award_info": text2.strip() if text2 else "",
                "extract_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return page_info_data
        except Exception as e:
            return None
    
    async def wait_for_start_time(self, start_time, running_flag=None):
        """等待开始时间"""
        last_log_time = 0
        while datetime.now() < start_time and (not running_flag or running_flag()):
            remaining = (start_time - datetime.now()).total_seconds()
            current_time = time.time()
            
            # 每1秒输出一次日志
            if current_time - last_log_time >= 1 and remaining > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待开始时间，剩余: {remaining:.2f}秒")
                last_log_time = current_time
            
            # 当剩余时间少于5秒时，每0.5秒输出一次日志
            elif remaining < 5 and remaining > 0 and current_time - last_log_time >= 0.5:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 即将开始，剩余: {remaining:.2f}秒")
                last_log_time = current_time
            
            await asyncio.sleep(0.1)
    
    async def perform_task_clicks(self, page, task_id, target_selector, interval, duration, results, running_flag=None):
        """执行任务点击"""
        click_count = 0
        success_count = 0
        fail_count = 0
        end_time = time.perf_counter() + duration
        start_time = datetime.now()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行点击任务: {task_id}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 点击参数: 持续时间={duration}s, 间隔={interval}s, 选择器={target_selector}")
        
        last_log_time = 0
        while time.perf_counter() < end_time and (not running_flag or running_flag()):
            try:
                await page.click(target_selector, timeout=50)
                success_count += 1
            except Exception as e:
                fail_count += 1
                # 每10次失败输出一次日志
                if fail_count % 10 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 已失败 {fail_count} 次")
            click_count += 1
            
            # 每100次点击输出一次日志
            if click_count % 100 == 0:
                elapsed = time.perf_counter() - (end_time - duration)
                rate = click_count / elapsed if elapsed > 0 else 0
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: 已点击 {click_count} 次，成功 {success_count} 次，速率: {rate:.2f}次/秒")
            
            if interval > 0 and (not running_flag or running_flag()):
                await asyncio.sleep(interval)
        
        # 计算实际执行时间
        actual_duration = (datetime.now() - start_time).total_seconds()
        # 计算成功率
        success_rate = (success_count / click_count * 100) if click_count > 0 else 0
        # 计算点击速率
        click_rate = (click_count / actual_duration) if actual_duration > 0 else 0
        
        result = f"{actual_duration:.2f}秒点击结束，共点击 {click_count} 次，成功 {success_count} 次，成功率 {success_rate:.1f}%，速率 {click_rate:.2f}次/秒"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {task_id}: {result}")
        
        results[task_id] = (True, result)
    
    def get_device_name(self):
        """获取设备名称"""
        from .utils import utils
        return utils.get_windows_device_name()
    
    async def login_bilibili(self):
        """B站登录功能"""
        playwright = await self.setup_browser()
        context = None
        page = None
        
        try:
            # 启动浏览器
            context = await self.launch_browser(playwright)
            
            # 打开B站登录页面
            page = await context.new_page()
            await page.goto("https://passport.bilibili.com/login", timeout=60000)
            
            # 等待页面加载完成
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            # 等待用户登录完成
            print("请在浏览器中完成B站登录...")
            print("登录完成后，请关闭浏览器窗口")
            
            # 循环检查页面是否仍然存在
            while True:
                try:
                    # 尝试获取页面标题，判断页面是否存在
                    await page.title()
                    await asyncio.sleep(2)
                except Exception:
                    # 页面不存在（已关闭），退出循环
                    break
            
            return True, "登录完成"
            
        except Exception as e:
            return False, f"登录失败: {str(e)}"
        finally:
            # 清理资源
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if playwright:
                try:
                    await playwright.stop()
                except Exception:
                    pass
