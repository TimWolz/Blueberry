import sys, os
from gui import Window
from PyQt5.QtWidgets import QApplication


if __name__ == "__main__":
    os.system('xset dpms 60 60 60')
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec_())