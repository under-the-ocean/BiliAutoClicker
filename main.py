import customtkinter as ctk
from src.gui import AutoClickerGUI
from src.config import config_manager

# 打印作者信息
print("作者：ocean之下")
print("作者主页：https://space.bilibili.com/3546571704634103")
print(f"服务端地址：{config_manager.client_config['server_url']}（可通过client_config.json修改）")
print("使用前需用autowatch登录！")

def main():
    """主函数"""
    # 设置界面缩放
    if hasattr(ctk, "set_widget_scaling"):
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
    
    # 创建根窗口
    root = ctk.CTk()
    
    # 创建应用实例
    app = AutoClickerGUI(root)
    
    # 启动主事件循环
    root.mainloop()

if __name__ == "__main__":
    main()
