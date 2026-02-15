import threading
import asyncio
import os
import customtkinter as ctk
from tkinter import scrolledtext, messagebox, END, filedialog
from datetime import datetime
from .config import config_manager, APP_VERSION
from .utils import utils
from .logger import logger
from .server import Server
from .tasks import tasks

# 配置
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class AutoClickerGUI:
    def __init__(self, root):
        self.log("开始初始化GUI...")
        self.root = root
        self.root.title("B站自动点击器（服务端同步版）- by ocean之下")
        self.root.geometry("750x425")
        self.root.resizable(True, True)
        
        self.log("设置自定义字体...")
        self.custom_fonts = self.set_custom_fonts()
        
        # 核心配置变量
        self.log_text = None
        self.server_task_ids = {}
        self.running = False
        self.loop = None
        self.async_thread = None
        
        # 支持的浏览器类型
        self.supported_browsers = ["firefox", "chromium", "webkit", "chrome", "msedge"]
        
        # 检测系统中安装的浏览器
        self.log("检测系统中安装的浏览器...")
        self.detected_browsers, self.browser_paths = utils.detect_browsers()
        self.log(f"检测到的浏览器: {self.detected_browsers}")
        
        # 初始化
        self.log_file_path = logger.log_file_path
        self.current_version = APP_VERSION  # 当前版本号
        
        self.log("创建GUI组件...")
        self.create_widgets()
        self.log("GUI组件创建完成")
        
        # 初始化服务端
        self.log("初始化服务端...")
        self.server = Server(config_manager.client_config['server_url'])
        self.log("服务端初始化完成")
        
        self.log("从服务端拉取配置...")
        self.fetch_server_config()
        
        self.log("更新配置显示...")
        self.update_config_display()
        
        # 检查更新和获取公告
        self.log("检查更新...")
        self.check_for_updates()
        
        self.log("获取服务器公告...")
        self.fetch_announcements()
        
        self.log("居中窗口...")
        self.center_window()
        self.log("GUI初始化完成")
    
    def set_custom_fonts(self):
        import os
        from tkinter import font
        
        try:
            # 获取字体文件路径（支持PyInstaller打包）
            import sys
            if getattr(sys, 'frozen', False):
                # 打包环境
                base_dir = sys._MEIPASS
            else:
                # 开发环境
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            font_path = os.path.join(base_dir, "zh-cn.ttf")
            
            # 检查字体文件是否存在
            if not os.path.exists(font_path):
                self.log(f"字体文件不存在: {font_path}")
                # 使用系统默认字体
                font_family = font.nametofont("TkDefaultFont").actual()["family"]
            else:
                # 尝试使用ctypes加载字体文件（Windows系统）
                try:
                    import ctypes
                    # 添加字体资源
                    result = ctypes.windll.gdi32.AddFontResourceW(font_path)
                    if result > 0:
                        self.log(f"成功加载字体文件: {font_path}")
                        # 通知系统字体发生变化
                        ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
                    else:
                        self.log(f"加载字体文件失败: 系统返回错误")
                except Exception as e:
                    self.log(f"加载字体文件失败: {str(e)}")
                
                # 字体名称为 SDK_SC_WEB（zh-cn.ttf 的实际字体名）
                font_family = "SDK_SC_WEB"
            
            # 验证字体是否可用
            try:
                # 尝试创建字体实例
                test_font = ctk.CTkFont(family=font_family, size=12)
                self.log(f"字体 {font_family} 可用")
            except Exception as e:
                self.log(f"字体 {font_family} 不可用，使用系统默认字体: {str(e)}")
                # 使用系统默认字体
                font_family = font.nametofont("TkDefaultFont").actual()["family"]
            
            # 设置默认字体
            default_font = (font_family, 12)
            ctk.CTkFont.default_font = default_font
            ctk.set_widget_scaling(1.1)
            
            # 返回字体配置
            return {
                "default": ctk.CTkFont(family=font_family, size=12),
                "small": ctk.CTkFont(family=font_family, size=10),
                "medium": ctk.CTkFont(family=font_family, size=14),
                "large": ctk.CTkFont(family=font_family, size=16, weight="bold"),
                "monospace": ctk.CTkFont(family=font_family, size=11)
            }
        except Exception as e:
            self.log(f"字体设置失败: {str(e)}")
            # 使用系统默认字体
            font_family = font.nametofont("TkDefaultFont").actual()["family"]
            return {
                "default": ctk.CTkFont(family=font_family, size=12),
                "small": ctk.CTkFont(family=font_family, size=10),
                "medium": ctk.CTkFont(family=font_family, size=14),
                "large": ctk.CTkFont(family=font_family, size=16, weight="bold"),
                "monospace": ctk.CTkFont(family=font_family, size=11)
            }
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def center_window(self):
        self.root.update_idletasks()
        
        # 获取屏幕大小
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 获取当前窗口大小
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        
        # 计算最大允许的窗口大小（屏幕的90%）
        max_width = int(screen_width * 0.9)
        max_height = int(screen_height * 0.9)
        
        # 如果窗口大小超过最大允许大小，调整窗口大小
        if window_width > max_width or window_height > max_height:
            # 计算新的窗口大小，保持宽高比
            width_ratio = window_width / window_height
            if width_ratio > 1:
                # 宽度为限制因素
                new_width = max_width
                new_height = int(new_width / width_ratio)
                if new_height > max_height:
                    new_height = max_height
                    new_width = int(new_height * width_ratio)
            else:
                # 高度为限制因素
                new_height = max_height
                new_width = int(new_height * width_ratio)
                if new_width > max_width:
                    new_width = max_width
                    new_height = int(new_width / width_ratio)
            
            # 设置新的窗口大小
            self.root.geometry(f"{new_width}x{new_height}")
            self.root.update_idletasks()
            # 更新窗口大小变量
            window_width = new_width
            window_height = new_height
        
        # 计算居中位置
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        # 确保窗口位置不会为负数
        x = max(0, x)
        y = max(0, y)
        
        # 设置窗口位置
        self.root.geometry(f"+{x}+{y}")
    
    def create_widgets(self):
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)  # 减少外边距
        
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))  # 减少下边距
        
        # 标题和操作区
        title_row = ctk.CTkFrame(title_frame, fg_color="transparent")
        title_row.pack(fill="x")
        
        title_label = ctk.CTkLabel(title_row, text="B站自动点击器（服务端同步版）", font=self.custom_fonts["medium"])
        title_label.pack(side="left", anchor="w")
        
        # 添加菜单按钮
        menu_frame = ctk.CTkFrame(title_row, fg_color="transparent")
        menu_frame.pack(side="right", anchor="e")
        
        # 创建下拉菜单
        self.menu_var = ctk.StringVar(value="功能菜单")
        self.menu = ctk.CTkOptionMenu(
            menu_frame,
            values=["保存配置", "特殊功能", "B站登录", "手动上传结果", "上传日志文件", "退出"],
            variable=self.menu_var,
            command=self.handle_menu_selection,
            font=self.custom_fonts["small"]
        )
        self.menu.pack(side="right", padx=(0, 10))
        
        # 添加独立的TaskID按钮
        taskid_btn = ctk.CTkButton(
            menu_frame,
            text="TaskID管理",
            command=self.open_taskid_window,
            font=self.custom_fonts["small"]
        )
        taskid_btn.pack(side="right")
        
        # TaskID窗口实例
        self.taskid_window = None
        
        # 信息显示区 - 使用网格布局更紧凑
        info_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=(5, 0))
        
        # 设备信息和服务端信息
        device_server_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        device_server_frame.pack(fill="x")
        
        device_label = ctk.CTkLabel(device_server_frame, 
                                  text=f"设备：{utils.get_windows_device_name()}",
                                  font=self.custom_fonts["small"])
        device_label.pack(side="left", padx=(0, 15))
        
        server_label = ctk.CTkLabel(device_server_frame, 
                                  text=f"服务端：{config_manager.client_config['server_url']}",
                                  font=self.custom_fonts["small"])
        server_label.pack(side="left", padx=(0, 15))
        
        cookie_label = ctk.CTkLabel(device_server_frame, 
                                  text=f"Cookie路径：{os.path.basename(config_manager.get_cookies_dir())}",
                                  font=self.custom_fonts["small"])
        cookie_label.pack(side="left")
        
        # 浏览器选择控件
        browser_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        browser_frame.pack(fill="x", pady=(5, 0))
        
        ctk.CTkLabel(browser_frame, text="浏览器:", font=self.custom_fonts["small"]).pack(side="left", padx=(0, 5))
        
        # 确定默认浏览器
        default_browser = config_manager.browser_config.get("browser_type", "chromium")
        # 如果配置的浏览器不在检测列表中，但检测到了其他浏览器，使用检测到的第一个浏览器
        if default_browser not in self.detected_browsers and self.detected_browsers:
            default_browser = self.detected_browsers[0]
        
        self.browser_var = ctk.StringVar(value=default_browser)
        browser_dropdown = ctk.CTkComboBox(
            browser_frame,
            values=self.supported_browsers,
            variable=self.browser_var,
            width=90,
            font=self.custom_fonts["small"],
            command=self.change_browser
        )
        browser_dropdown.pack(side="left", padx=(0, 15))
        
        # 浏览器路径选择控件
        ctk.CTkLabel(browser_frame, text="路径:", font=self.custom_fonts["small"]).pack(side="left", padx=(0, 5))
        
        # 确定默认浏览器路径
        default_browser_path = config_manager.browser_config.get("browser_executable_path", "")
        # 如果配置的路径为空，但默认浏览器有检测到的路径，使用检测到的路径
        if not default_browser_path and default_browser in self.browser_paths:
            default_browser_path = self.browser_paths[default_browser]
        
        self.browser_path_var = ctk.StringVar(value=default_browser_path)
        browser_path_entry = ctk.CTkEntry(
            browser_frame,
            textvariable=self.browser_path_var,
            width=250,
            font=self.custom_fonts["small"]
        )
        browser_path_entry.pack(side="left", padx=(0, 5))
        
        select_path_btn = ctk.CTkButton(
            browser_frame,
            text="浏览",
            command=self.select_browser_path,
            width=50,
            font=self.custom_fonts["small"]
        )
        select_path_btn.pack(side="left", padx=(0, 5))
        
        save_path_btn = ctk.CTkButton(
            browser_frame,
            text="保存",
            command=self.save_browser_config,
            width=50,
            font=self.custom_fonts["small"]
        )
        save_path_btn.pack(side="left")
        
        # 日志文件信息显示
        log_author_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        log_author_frame.pack(fill="x", pady=(5, 0))
        
        log_info_label = ctk.CTkLabel(log_author_frame, 
                                    text=f"日志文件：{os.path.basename(logger.get_log_file_path())}",
                                    font=self.custom_fonts["small"])
        log_info_label.pack(side="left", anchor="w")
        
        author_label = ctk.CTkLabel(log_author_frame, 
                                  text="作者: ocean之下",
                                  font=self.custom_fonts["small"])
        author_label.pack(side="right", anchor="e")
        
        paned_window = ctk.CTkFrame(main_frame)
        paned_window.pack(fill="both", expand=True)
        
        # 只保留右侧的任务配置区域
        right_frame = ctk.CTkFrame(paned_window)
        right_frame.pack(fill="both", expand=True)
        
        config_frame = ctk.CTkFrame(right_frame, corner_radius=8)
        config_frame.pack(fill="both", pady=(0, 8))
        
        ctk.CTkLabel(config_frame, text="任务配置", font=self.custom_fonts["small"]).pack(anchor="w", pady=(8, 3), padx=8)
        
        table_container = ctk.CTkFrame(config_frame)
        table_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        
        self.config_text = ctk.CTkTextbox(table_container, height=100, font=self.custom_fonts["monospace"])
        self.config_text.pack(fill="both", expand=True)
        self.config_text.configure(state="disabled")
        
        button_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=8, pady=(0, 8))
        
        ctk.CTkButton(button_frame, text="编辑", command=self.edit_selected_task, width=60, font=self.custom_fonts["small"]).pack(side="left", padx=(0, 4))
        ctk.CTkButton(button_frame, text="删除", command=self.remove_selected_task, width=60, font=self.custom_fonts["small"]).pack(side="left", padx=4)
        ctk.CTkButton(button_frame, text="默认值", command=self.apply_defaults, width=60, font=self.custom_fonts["small"]).pack(side="left", padx=4)
        ctk.CTkButton(button_frame, text="清空", command=self.clear_all_tasks, width=60, font=self.custom_fonts["small"]).pack(side="left", padx=4)
        
        # 任务控制按钮
        control_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        control_frame.pack(fill="x", pady=(8, 0))
        
        self.start_button = ctk.CTkButton(control_frame, text="开始任务", command=self.start_tasks, font=self.custom_fonts["small"])
        self.start_button.pack(side="left", padx=(0, 8))
        
        self.stop_button = ctk.CTkButton(control_frame, text="停止任务", command=self.stop_tasks, state="disabled", font=self.custom_fonts["small"])
        self.stop_button.pack(side="left", padx=8)
    
    def update_task_list(self):
        """更新TaskID列表，现在更新的是TaskID窗口中的列表"""
        self.update_taskid_window_list()
    
    def on_checkbox_change(self, task_key, var):
        task_value = self.server_task_ids.get(task_key, "")
        if task_value:
            if var.get() and task_value not in tasks.selected_tasks:
                tasks.selected_tasks.append(task_value)
            elif not var.get() and task_value in tasks.selected_tasks:
                tasks.selected_tasks.remove(task_value)
    
    def fetch_server_config(self):
        self.log("正在从服务端拉取配置...")
        success, server_config, server_task_ids, error_message = self.server.fetch_server_config()
        
        if success:
            self.server_task_ids = server_task_ids
            self.log(f"✅ 服务端配置拉取成功，获取{len(server_task_ids)}个TaskID")
            for key, val in server_task_ids.items():
                self.log(f"  - {key}: {val}")
        else:
            self.server_task_ids = {
                "1": "18ERA1wloghwww000",
                "2": "18ERA1wloghwz800",
                "3": "18ERA1wloghwf700"
            }
            self.log(f"❌ 服务端配置拉取失败：{error_message}")
            self.log("⚠️ 降级使用本地默认TaskID列表")
        
        self.update_task_list()
    
    def refresh_server_config(self):
        self.log("正在手动刷新服务端配置...")
        self.fetch_server_config()
        self.log("服务端配置刷新完成！")
    
    def add_selected_tasks(self):
        added_count = 0
        for task_key, var in self.task_vars.items():
            if var.get():
                task_value = self.server_task_ids.get(task_key, "")
                if task_value:
                    success, message = tasks.add_task(task_value)
                    if success:
                        added_count += 1
        if added_count > 0:
            self.log(f"已添加 {added_count} 个服务端TaskID到配置")
            self.update_config_display()
        else:
            messagebox.showinfo("提示", "请先勾选服务端TaskID")
    
    def add_manual_task(self):
        task_id = self.manual_task_var.get().strip()
        if task_id:
            success, message = tasks.add_task(task_id)
            if success:
                self.manual_task_var.set("")
                self.log(f"已添加手动TaskID: {task_id}")
                self.update_config_display()
            else:
                self.log("TaskID已存在")
        else:
            messagebox.showwarning("警告", "请输入TaskID")
    
    def update_config_display(self):
        def update_display():
            self.config_text.configure(state="normal")
            self.config_text.delete("1.0", "end")
            if tasks.task_configs:
                header = f"{'TaskID':<30}{'开始时间':<15}{'点击间隔':<10}{'持续时间':<10}\n"
                self.config_text.insert("end", header)
                self.config_text.insert("end", "-" * 65 + "\n")
                for task_id, config in tasks.task_configs.items():
                    start_time_str = config['start_time'].strftime("%H:%M:%S") if isinstance(config['start_time'], datetime) else str(config['start_time'])
                    row = f"{task_id:<30}{start_time_str:<15}{config['interval']:<10.2f}{config['duration']:<10.1f}\n"
                    self.config_text.insert("end", row)
            else:
                self.config_text.insert("end", "暂无任务配置")
            self.config_text.configure(state="disabled")
        
        if threading.current_thread() == threading.main_thread():
            update_display()
        else:
            self.root.after(0, update_display)
    
    def save_task_configs(self):
        success, message = tasks.save_task_configs()
        if success:
            self.log("✅ 任务配置保存成功")
            messagebox.showinfo("成功", "任务配置已保存")
        else:
            self.log(f"❌ 保存任务配置失败: {message}")
            messagebox.showerror("错误", f"保存配置失败: {message}")
    
    def edit_selected_task(self):
        if not tasks.task_configs:
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
        task_var = ctk.StringVar(value=list(tasks.task_configs.keys())[0])
        task_combo = ctk.CTkComboBox(form_frame, values=list(tasks.task_configs.keys()), variable=task_var, font=self.custom_fonts["default"])
        task_combo.grid(row=0, column=1, sticky="ew", pady=8, padx=(10, 0))
        
        current_config = tasks.task_configs[task_var.get()]
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
        
        def save_changes():
            try:
                task_id = task_var.get()
                new_start = start_var.get()
                new_interval = interval_var.get()
                new_duration = duration_var.get()
                success, message = tasks.update_task(task_id, new_start, new_interval, new_duration)
                if success:
                    dialog.destroy()
                    self.log(f"已更新TaskID {task_id} 的配置")
                    self.update_config_display()
                else:
                    messagebox.showerror("错误", message)
            except ValueError as e:
                messagebox.showerror("错误", f"输入格式错误: {str(e)}")
        
        def confirm_changes():
            if messagebox.askyesno("确认", "确定要保存这些更改吗？"):
                save_changes()
        
        ctk.CTkButton(button_frame, text="确认", command=confirm_changes, width=80, font=self.custom_fonts["default"]).pack(side="right", padx=(0, 8))
        ctk.CTkButton(button_frame, text="取消", command=dialog.destroy, width=80, font=self.custom_fonts["default"]).pack(side="right")
        
        update_preview()
    
    def remove_selected_task(self):
        if not tasks.task_configs:
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
        
        task_var = ctk.StringVar(value=list(tasks.task_configs.keys())[0])
        task_combo = ctk.CTkComboBox(main_frame, values=list(tasks.task_configs.keys()), variable=task_var, font=self.custom_fonts["default"])
        task_combo.pack(pady=10, fill="x")
        
        ctk.CTkLabel(main_frame, text="删除后无法恢复，确定要删除吗？", font=self.custom_fonts["small"], text_color="red").pack(pady=(10, 5))
        
        def delete_task():
            task_id = task_var.get()
            success, message = tasks.remove_task(task_id)
            dialog.destroy()
            self.log(f"已删除TaskID: {task_id}")
            self.update_config_display()
        
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=5)
        
        ctk.CTkButton(button_frame, text="删除", command=delete_task, font=self.custom_fonts["default"]).pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(button_frame, text="取消", command=dialog.destroy, font=self.custom_fonts["default"]).pack(side="left", padx=5, fill="x", expand=True)
    
    def apply_defaults(self):
        success, message = tasks.apply_defaults()
        if success:
            self.log(message)
            self.update_config_display()
    
    def clear_all_tasks(self):
        if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
            success, message = tasks.clear_all_tasks()
            if success:
                self.log(message)
                self.update_config_display()
                for var in self.task_vars.values():
                    var.set(False)
    
    def clear_log(self):
        pass  # 由于移除了日志窗口，此方法不再需要
    
    def handle_menu_selection(self, selection):
        """处理菜单选择事件"""
        if selection == "保存配置":
            self.save_task_configs()
        elif selection == "特殊功能":
            self.open_special_features()
        elif selection == "B站登录":
            self.login_bilibili()
        elif selection == "手动上传结果":
            self.trigger_batch_upload()
        elif selection == "上传日志文件":
            self.trigger_log_upload()
        elif selection == "退出":
            self.root.quit()
    
    def check_for_updates(self):
        """检查更新"""
        self.log("正在检查更新...")
        success, update_info = self.server.check_update(self.current_version)
        
        if success:
            if update_info.get("has_update"):
                self.log(f"发现新版本：{update_info.get('version')}")
                self.log(f"更新内容：{update_info.get('description')}")
                self.log(f"下载链接：{update_info.get('download_url')}")
                # 显示更新提示对话框
                self.show_update_dialog(update_info)
            else:
                self.log("当前已是最新版本")
        else:
            self.log(f"检查更新失败：{update_info.get('message', '未知错误')}")
    
    def fetch_announcements(self):
        """获取服务器公告"""
        self.log("正在获取服务器公告...")
        success, announcements = self.server.get_announcements()
        
        if success:
            if announcements:
                self.log(f"获取到 {len(announcements)} 条公告")
                # 显示公告对话框
                self.show_announcements_dialog(announcements)
            else:
                self.log("暂无公告")
        else:
            self.log(f"获取公告失败：{announcements.get('message', '未知错误')}")
    
    def show_update_dialog(self, update_info):
        """显示更新提示对话框"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("发现新版本")
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main_frame, text="发现新版本", font=self.custom_fonts["large"]).pack(anchor="w", pady=(0, 15))
        
        ctk.CTkLabel(main_frame, text=f"当前版本：{self.current_version}", font=self.custom_fonts["default"]).pack(anchor="w", pady=(5, 0))
        ctk.CTkLabel(main_frame, text=f"最新版本：{update_info.get('version')}", font=self.custom_fonts["default"]).pack(anchor="w", pady=(5, 0))
        
        ctk.CTkLabel(main_frame, text="更新内容：", font=self.custom_fonts["default"]).pack(anchor="w", pady=(10, 5))
        update_text = ctk.CTkTextbox(main_frame, height=100, font=self.custom_fonts["small"])
        update_text.pack(fill="x", pady=(0, 10))
        update_text.insert("1.0", update_info.get('description', ''))
        update_text.configure(state="disabled")
        
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(button_frame, text="稍后再说", command=dialog.destroy, width=80, font=self.custom_fonts["default"]).pack(side="right", padx=(0, 8))
        ctk.CTkButton(button_frame, text="立即下载", command=lambda: self.open_download_link(update_info.get('download_url')), width=80, font=self.custom_fonts["default"]).pack(side="right")
    
    def show_announcements_dialog(self, announcements):
        """显示公告对话框"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("服务器公告")
        dialog.geometry("500x400")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main_frame, text="服务器公告", font=self.custom_fonts["large"]).pack(anchor="w", pady=(0, 15))
        
        announcements_text = ctk.CTkTextbox(main_frame, height=250, font=self.custom_fonts["small"])
        announcements_text.pack(fill="both", expand=True, pady=(0, 10))
        
        for announcement in announcements:
            title = announcement.get('title', '无标题')
            content = announcement.get('content', '无内容')
            date = announcement.get('date', '未知日期')
            announcements_text.insert("end", f"【{title}】({date})\n")
            announcements_text.insert("end", f"{content}\n\n")
        
        announcements_text.configure(state="disabled")
        
        ctk.CTkButton(main_frame, text="关闭", command=dialog.destroy, width=80, font=self.custom_fonts["default"]).pack(side="right")
    
    def open_download_link(self, url):
        """打开下载链接"""
        import webbrowser
        webbrowser.open(url)
    
    def change_browser(self, event=None):
        """改变浏览器类型"""
        browser_type = self.browser_var.get()
        self.log(f"浏览器已切换为: {browser_type}")
        
        # 如果检测到该浏览器的路径，自动填充
        if browser_type in self.browser_paths:
            self.browser_path_var.set(self.browser_paths[browser_type])
            self.log(f"自动填充浏览器路径: {self.browser_paths[browser_type]}")
    
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
            self.log(f"已选择浏览器路径: {file_path}")
    
    def save_browser_config(self):
        """保存浏览器配置"""
        browser_type = self.browser_var.get()
        browser_executable_path = self.browser_path_var.get()
        success = config_manager.save_browser_config(browser_type, browser_executable_path)
        if success:
            self.log("✅ 浏览器配置已保存")
            messagebox.showinfo("成功", "浏览器配置已保存")
        else:
            self.log("❌ 保存浏览器配置失败")
            messagebox.showerror("错误", "保存浏览器配置失败")
    
    def start_tasks(self):
        if not tasks.task_configs:
            messagebox.showwarning("警告", "请先添加任务")
            return
        # 清空之前的结果缓存
        tasks.reward_result_cache.clear()
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        
        # 在单独的线程中运行异步任务
        self.async_thread = threading.Thread(target=self.run_async_tasks, daemon=True)
        self.async_thread.start()
    
    def stop_tasks(self):
        self.running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.log("正在停止任务...")
    
    def run_async_tasks(self):
        """在单独的线程中运行异步任务"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 为Windows设置正确的事件循环策略
            import sys
            if sys.platform.startswith('win'):
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            # 运行主异步函数
            success, message = loop.run_until_complete(tasks.execute_tasks(
                config_manager.browser_config.get("browser_type", "chromium"),
                config_manager.browser_config.get("browser_executable_path"),
                config_manager.get_cookies_dir(),
                config_manager.client_config['server_url'],
                lambda: self.running
            ))
            
            self.log(f"\n=== 任务执行结果 ===")
            self.log(message)
            
        except Exception as e:
            self.log(f"任务执行错误: {str(e)}")
        finally:
            # 清理资源
            self.running = False
            # 检查是否全局禁用关机功能
            disable_shutdown = config_manager.server_config.get("disable_shutdown", False)
            if not disable_shutdown and config_manager.special_features["auto_shutdown"]["enabled"]:
                utils.schedule_shutdown(config_manager.special_features["auto_shutdown"]["delay_minutes"])
            
            # 在主线程中更新GUI状态
            def update_gui():
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
            
            self.root.after(0, update_gui)
    
    def trigger_batch_upload(self):
        if not tasks.reward_result_cache and not tasks.task_configs:
            messagebox.showinfo("提示", "没有任务结果可上传")
            return
        threading.Thread(target=self.batch_upload_results, daemon=True).start()
    
    def batch_upload_results(self):
        server = Server(config_manager.client_config['server_url'])
        success, message = server.batch_upload_results(tasks.reward_result_cache, tasks.task_configs)
        if success:
            self.log(f"✅ {message}")
        else:
            self.log(f"❌ {message}")
    
    def trigger_log_upload(self):
        threading.Thread(target=self.upload_log_file, daemon=True).start()
    
    def upload_log_file(self):
        success, message = logger.upload_log_file(config_manager.client_config['server_url'])
        if success:
            self.log(f"✅ {message}")
        else:
            self.log(f"❌ {message}")
    
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
        
        shutdown_enabled_var = ctk.BooleanVar(value=config_manager.special_features["auto_shutdown"]["enabled"])
        ctk.CTkCheckBox(
            shutdown_frame,
            text="任务完成后自动关机",
            variable=shutdown_enabled_var,
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
        
        shutdown_delay_var = ctk.StringVar(value=str(config_manager.special_features["auto_shutdown"]["delay_minutes"]))
        ctk.CTkEntry(
            delay_frame,
            textvariable=shutdown_delay_var,
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
            command=lambda: utils.cancel_shutdown() and self.log("已取消自动关机"),
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
                config_manager.special_features["auto_shutdown"]["enabled"] = shutdown_enabled_var.get()
                config_manager.special_features["auto_shutdown"]["delay_minutes"] = int(shutdown_delay_var.get())
                success = config_manager.save_special_features_config()
                if success:
                    self.log("✅ 特殊功能配置保存成功")
                    messagebox.showinfo("成功", "特殊功能配置已保存")
                    dialog.destroy()
                else:
                    messagebox.showerror("错误", "保存特殊功能配置失败")
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
    
    def login_bilibili(self):
        """B站登录功能"""
        self.log("正在启动B站登录...")
        
        # 创建Browser实例
        from .browser import Browser
        browser = Browser(
            config_manager.browser_config.get("browser_type", "chromium"),
            config_manager.browser_config.get("browser_executable_path"),
            config_manager.get_cookies_dir()
        )
        
        # 在单独的线程中运行登录过程
        def run_login():
            try:
                import asyncio
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 为Windows设置正确的事件循环策略
                import sys
                if sys.platform.startswith('win'):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
                # 运行登录
                success, message = loop.run_until_complete(browser.login_bilibili())
                
                # 在主线程中更新日志
                def update_log():
                    if success:
                        self.log(f"✅ B站登录成功: {message}")
                    else:
                        self.log(f"❌ B站登录失败: {message}")
                
                self.root.after(0, update_log)
                
            except Exception as e:
                def update_error_log():
                    self.log(f"❌ 登录过程中发生错误: {str(e)}")
                self.root.after(0, update_error_log)
        
        # 启动登录线程
        login_thread = threading.Thread(target=run_login, daemon=True)
        login_thread.start()
    
    def open_taskid_window(self):
        """打开服务端TaskID窗口"""
        # 如果窗口已存在，先关闭
        if self.taskid_window and self.taskid_window.winfo_exists():
            self.taskid_window.destroy()
        
        # 创建新窗口
        self.taskid_window = ctk.CTkToplevel(self.root)
        self.taskid_window.title("服务端TaskID管理")
        self.taskid_window.geometry("400x500")
        self.taskid_window.resizable(True, True)
        self.taskid_window.transient(self.root)
        
        # 设置窗口位置
        self.taskid_window.update_idletasks()
        x = self.root.winfo_x() + 50
        y = self.root.winfo_y() + 50
        self.taskid_window.geometry(f"+{x}+{y}")
        
        # 创建窗口内容
        main_frame = ctk.CTkFrame(self.taskid_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        ctk.CTkLabel(main_frame, text="服务端TaskID列表", font=self.custom_fonts["medium"]).pack(anchor="w", pady=(5, 10))
        
        # 刷新按钮
        refresh_btn = ctk.CTkButton(main_frame, text="刷新服务端TaskID", command=self.refresh_server_config, font=self.custom_fonts["small"])
        refresh_btn.pack(anchor="w", pady=(0, 10))
        
        # TaskID列表区域
        list_frame = ctk.CTkFrame(main_frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # 创建可滚动框架
        self.taskid_scrollable_frame = ctk.CTkScrollableFrame(list_frame)
        self.taskid_scrollable_frame.pack(fill="both", expand=True)
        
        # 显示TaskID列表
        self.update_taskid_window_list()
        
        # 添加选中按钮
        add_selected_btn = ctk.CTkButton(main_frame, text="添加选中TaskID", command=self.add_selected_tasks, font=self.custom_fonts["default"])
        add_selected_btn.pack(fill="x", pady=(0, 10))
        
        # 手动输入TaskID
        ctk.CTkLabel(main_frame, text="手动输入TaskID", font=self.custom_fonts["default"]).pack(anchor="w", pady=(0, 5))
        
        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=(0, 10))
        
        self.manual_task_var = ctk.StringVar()
        task_entry = ctk.CTkEntry(input_frame, textvariable=self.manual_task_var, placeholder_text="输入TaskID", font=self.custom_fonts["default"])
        task_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        add_manual_btn = ctk.CTkButton(input_frame, text="添加", command=self.add_manual_task, width=60, font=self.custom_fonts["default"])
        add_manual_btn.pack(side="right")
    
    def update_taskid_window_list(self):
        """更新TaskID窗口中的列表"""
        if not hasattr(self, 'taskid_scrollable_frame'):
            return
        
        # 清空现有内容
        for widget in self.taskid_scrollable_frame.winfo_children():
            widget.destroy()
        
        # 重新创建复选框
        self.task_checkboxes = {}
        self.task_vars = {}
        
        if self.server_task_ids:
            for task_key, task_value in self.server_task_ids.items():
                var = ctk.BooleanVar()
                checkbox = ctk.CTkCheckBox(
                    self.taskid_scrollable_frame,
                    text=f"{task_key}. {task_value}",
                    variable=var,
                    font=self.custom_fonts["default"],
                    command=lambda k=task_key, v=var: self.on_checkbox_change(k, v)
                )
                checkbox.pack(anchor="w", pady=2, padx=5)
                self.task_checkboxes[task_key] = checkbox
                self.task_vars[task_key] = var
        else:
            tip_label = ctk.CTkLabel(self.taskid_scrollable_frame, text="暂无服务端TaskID数据", font=self.custom_fonts["small"], text_color="#666")
            tip_label.pack(anchor="w", pady=5, padx=5)
    
    def refresh_server_config(self):
        """刷新服务端配置"""
        self.log("正在手动刷新服务端配置...")
        self.fetch_server_config()
        self.log("服务端配置刷新完成！")
        # 更新TaskID窗口列表
        self.update_taskid_window_list()
