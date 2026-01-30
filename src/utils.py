import os
import sys
import hashlib
import subprocess
from datetime import datetime, timedelta

class Utils:
    @staticmethod
    def get_windows_device_name():
        """获取Windows系统的设备名称（计算机名）"""
        try:
            if sys.platform.startswith('win32'):
                return os.environ.get('COMPUTERNAME', f"windows_device_{os.getpid()}")
            else:
                import socket
                return socket.gethostname()
        except Exception as e:
            return f"unknown_device_{str(e)[:8]}"
    
    @staticmethod
    def get_device_id():
        """获取设备ID"""
        system_info = f"{sys.platform}-{os.name}-{os.getlogin()}"
        return hashlib.md5(system_info.encode()).hexdigest()[:16]
    
    @staticmethod
    def parse_time_input(time_str, default_time="00:29:57"):
        """解析时间输入"""
        time_str = time_str.strip()
        if not time_str:
            return Utils.parse_time_input(default_time)
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
    
    @staticmethod
    def schedule_shutdown(delay_minutes):
        """计划关机"""
        try:
            delay_seconds = delay_minutes * 60
            if sys.platform.startswith('win'):
                subprocess.run(f"shutdown /s /t {delay_seconds}", shell=True, check=True)
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                subprocess.run(f"shutdown -h +{delay_minutes}", shell=True, check=True)
            else:
                return False
            return True
        except Exception as e:
            return False
    
    @staticmethod
    def cancel_shutdown():
        """取消关机"""
        try:
            if sys.platform.startswith('win'):
                subprocess.run("shutdown /a", shell=True, check=True)
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
                subprocess.run("shutdown -c", shell=True, check=True)
            else:
                return False
            return True
        except Exception as e:
            return False
    
    @staticmethod
    def get_exe_directory():
        """获取可执行文件目录"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            return os.path.dirname(os.path.abspath(__file__))

# 全局工具类实例
utils = Utils()
