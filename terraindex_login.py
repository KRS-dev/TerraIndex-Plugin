import os
from pickle import NONE
import requests, json
from typing import Tuple
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


        self.username.setText(username)
        self.password.setText(password)
        self.licensenumber = str(licensenumber)
        self.applicationcode = str(applicationcode)
        # self.licensenumber.setText(str(licensenumber))
        # self.applicationcode.setText(str(applicationcode))
        self.message.setText(message)

        
    
    def getToken(self) -> Tuple[bool, object, str, str, int, int]:
        """Sends a request to web.terraindex.com for a application login token.

        Returns
        -------
        Tuple[bool, object, str, str, int, int]
            request result, json dict, username, password, licensenumber, applicationcode
        """        
        results = None
        if self.result() == 1:
            url = r'https://web.terraindex.com/ReportWS/tokenmanager/ReportingToken'

            body = {
                'Username': self.username.text(),
                'Password': self.password.text(),
                'Licensenumber': self.licensenumber,
                'ApplicationCode': self.applicationcode
            }

            headers = {
                'Content-Type': 'application/json'
            }


            r = requests.post(url=url, data=json.dumps(body), headers=headers)
            results = r.json()

        # self.result() = 1 if Ok clicked, 0 if cancelled or closed
        return self.result(), results, self.username.text(), self.password.text(), self.licensenumber, self.applicationcode