"""PyInstaller 的 GUI 入口；保持包内相对导入在冻结后正常工作。"""

from douhot_crawler.gui import main


if __name__ == "__main__":
    main()
