import os

from qgis.PyQt import QtGui, QtWidgets, uic


FORM_CLASS, BASE_CLASS = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'terraindex_login.ui'))


class TerraIndexLoginDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, username='', password='', licensenumber=613, applicationcode=98, message='', parent=None):

        super().__init__()

        #self.ui = uic.loadUi(os.path.join(
        #    os.path.dirname(__file__), 'terraindex_login.ui'), self)
        self.setupUi(self)
        self.setModal(True)


        self.username.setText(str(username))
        self.password.setText(str(password))
        self.licensenumber.setText(str(licensenumber))
        self.applicationcode.setText(str(applicationcode))
        self.message.setText(str(message))

        
    
    def getCredentials(self):
  
        # self.result() = 1 if Ok clicked, 0 if cancelled or closed
        return self.result(), self.username.text(), self.password.text(), self.licensenumber.text(), self.applicationcode.text()