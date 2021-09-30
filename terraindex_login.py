import os

from qgis.PyQt import QtGui, QtWidgets, uic


FORM_CLASS, BASE_CLASS = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'terraindex_login.ui'))


class TerraIndexLoginDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, username=None, password=None, licensenumber=None, applicationcode=None, message=None, parent=None):

        super().__init__()

        #self.ui = uic.loadUi(os.path.join(
        #    os.path.dirname(__file__), 'terraindex_login.ui'), self)

        self.setupUi(self)

        self.username.text = username
        self.password.text = password
        self.licensenumber.text = licensenumber
        self.applicationcode.text = applicationcode
        self.message.text = message

        
    
    def getCredentials(self):
        # self.result() = 1 if Ok clicked, 0 if cancelled or closed
        return self.result(), self.username.text, self.password.text, self.licensenumber.text, self.applicationcode.text