import subprocess
import platform
import sys
import shlex  # 用于安全地分割字符串为列表，处理带引号的参数


def build_with_nuitka():
    print(f"Detected OS: {platform.system()}")

    # 基础 Nuitka 命令参数列表
    nuitka_command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--enable-console",
        "--output-filename=modfetch.bin",
        "--windows-icon-from-ico=logo/logo.ico",
        "--linux-icon=logo/logo_raw.png",
        "--assume-yes-for-downloads",
        "modfetch/__main__.py",
    ]
    print("\nStarting Nuitka build process with command:")
    # 打印将要执行的命令，方便调试
    print(" ".join(shlex.quote(arg) for arg in nuitka_command))
    print("-" * 50)

    try:
        # 使用 subprocess.run，并传入列表形式的命令，无需 shell=True
        # check=True 会在命令返回非零退出码时抛出 CalledProcessError
        subprocess.run(
            nuitka_command,
            check=True,
        )
        print("-" * 50)
        print("Nuitka build process finished successfully!")
        print(
            f"Executable 'modfetch' created in: {subprocess.run(['pwd'], capture_output=True, text=True, check=True).stdout.strip()}"
        )

    except subprocess.CalledProcessError as e:
        print("-" * 50)
        print(f"Error during Nuitka build:")
        print(f"Command: {e.cmd}")
        print(f"Return Code: {e.returncode}")
        if e.stdout:
            print(f"Stdout:\n{e.stdout}")
        if e.stderr:
            print(f"Stderr:\n{e.stderr}")
        sys.exit(1)  # 错误时退出脚本

    except FileNotFoundError:
        print("-" * 50)
        print("Error: Nuitka or Python executable not found.")
        print(
            "Please ensure Nuitka is installed in your virtual environment and the virtual environment is activated, or Nuitka is in your system PATH."
        )
        sys.exit(1)


if __name__ == "__main__":
    build_with_nuitka()
