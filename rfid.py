import cgi
import os
import datetime
import hashlib
import json
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

from google.appengine.api import urlfetch


def hasCard(user_name):
    user = Card.all().filter("username =",user_name)
    if user.count() != 0:
        if (user[0].hashedCard == ""):
            return False
        else:
            return True
    else:
        return False

class Card(db.Model):
    username = db.UserProperty()
    value = db.FloatProperty()
    hashedCard = db.StringProperty()
    lastAccessed = db.DateTimeProperty()

class Tools(db.Model):
    name = db.StringProperty()

class ToolAuthorizations(db.Model):
    username = db.UserProperty()
    tool = db.StringProperty()
    
class MainPage(webapp.RequestHandler):
    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))
            
        #determine if user has a card
        has_card = hasCard(self.user_name)
            
        template_values = {'username':self.user_name,
                           'has_card':has_card,
                           }
        self.response.out.write(template.render('templates/index.html', template_values))
         

class NewCard(webapp.RequestHandler):
    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))

        #determine if user has a card
        has_card = hasCard(self.user_name)
            
        template_values = {'username':self.user_name,
                           'has_card':has_card,}
        
        self.response.out.write(template.render('templates/newcard.html', template_values))
        
    def post(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))

        m = hashlib.sha224()
        m.update(str(self.request.get("card_code")))
        m.hexdigest()

        #determine if a user is already in the system
        user = Card.all().filter("username =",self.user_name)
        
        if user.count() == 0:
            #create new user in db if they don't exist
            newitem = Card()
            newitem.username        = self.user_name
            newitem.value           = 0.0
            newitem.hashedCard      = m.hexdigest()
            newitem.lastAccessed    = datetime.datetime.now()
            newitem.put()
        else:
            #if they do, only modify the card number
            for response in Card.all().filter("username =",self.user_name):
                response.hashedCard     = m.hexdigest()
                response.lastAccessed   = datetime.datetime.now()
                response.put()

        self.redirect('/')

class Cash(webapp.RequestHandler):
    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))

        #determine if user has a card
        has_card = hasCard(self.user_name)

        template_values = {'username':self.user_name,
                           'has_card':has_card,
                           }
        
        if has_card:
            #determine value of card
            user = Card.all().filter("username =",self.user_name)[0]
            template_values['value']=user.value
        
        self.response.out.write(template.render('templates/cash.html', template_values))

class Tools(webapp.RequestHandler):
    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))
                       
        tools = db.GqlQuery("SELECT * FROM ToolAuthorizations WHERE user=%s"%self.user_name)
        num_tools = items.count()
        has_tools = bool(num_tools)
        
        template_values = {'username': self.user_name,
                           'tools': tools,
                           'has_tools': has_tools,
                           }
        self.response.out.write(template.render('templates/tools.html', template_values))
        
class Administration(webapp.RequestHandler):
    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))
            

        template_values = {}
        self.response.out.write(template.render('templates/admin.html', template_values))
        
class Validate(webapp.RequestHandler):
    def post(self):
        self.rfid = self.request.get("rfid")
        
        m = hashlib.sha224()
        m.update(str(self.rfid))
        
        user = Card.all().filter("hashedCard =",m.hexdigest())
        if user.count() <=0:
            self.response.out.write('denied')
        else:
            
            output = json.dumps({'username':str(user[0].username),'status':'accepted'})
            self.response.out.write(output)

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/newcard', NewCard),
                                      ('/cash', Cash),
                                      ('/tools', Tools),
                                      ('/admin', Administration),
                                      ('/validate', Validate),
                                     ],
                                     debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
