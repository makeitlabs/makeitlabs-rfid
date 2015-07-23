import cgi
import os
import datetime
import hashlib
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import urlfetch
from django.utils import simplejson
from google.appengine.ext import webapp
from datetime import datetime
from datetime import tzinfo
from datetime import timedelta
from operator import itemgetter, attrgetter

domain = "@makeitlabs.com"

class UTC(tzinfo):
   def utcoffset(self, dt):
       return timedelta(0)
   def dst(self, dt):
       return timedelta(0)
   def tzname(self,dt):
       return "UTC"

class EasternTZ(tzinfo):
   """Implementation of the Eastern timezone."""
   def utcoffset(self, dt):
       return timedelta(hours=-5) + self.dst(dt)

   def _FirstSunday(self, dt):
       """First Sunday on or after dt."""
       return dt + timedelta(days=(6-dt.weekday()))

   def dst(self, dt):
       # 2 am on the second Sunday in March
       dst_start = self._FirstSunday(datetime(dt.year, 3, 8, 2))
       # 1 am on the first Sunday in November
       dst_end = self._FirstSunday(datetime(dt.year, 11, 1, 1))

       if dst_start <= dt.replace(tzinfo=None) < dst_end:
           return timedelta(hours=1)
       else:
           return timedelta(hours=0)
   def tzname(self, dt):
       if self.dst(dt) == timedelta(hours=0):
           return "EST"
       else:
           return "EDT"

SECRET_TOKEN = 'v820gFd9Wwmj8RjKl0maTLYtW3OPrXaatzNE7rbd'
#GMT_OFFSET = -4


def adminCheck(self):
   if not users.is_current_user_admin():
      self.response.out.write('''
            <html><body>
                    <h1>You need to be an admin.</h1>
            </body></html>''')
      return False
   return True


# check if a particular resource is allowed inside of a comma-delimited string of permissions
# e.g. check for 'wood' in a string of 'laser,wood,lift'
def resourceIsAllowed(resource, permstring):
        permlist = permstring.split(',')
        return any(resource in s for s in permlist)


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
   hashedCard = db.StringProperty()
   lastAccessed = db.DateTimeProperty()
   allowed = db.StringProperty()

class AccessLog(db.Model):
   timestamp = db.DateTimeProperty()
   rfidhash = db.StringProperty()
   username = db.UserProperty()
   result = db.StringProperty()
   resource = db.StringProperty()

class ResourceList(db.Model):
   name = db.StringProperty()
   description = db.StringProperty()


# build a resource name dictionary for faster lookups
RESOURCES = dict()
res = ResourceList.all().fetch(limit=16)
for r in res:
   RESOURCES[r.name] = r.description


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
            newitem.allowed         = 'allowed'
            newitem.hashedCard      = m.hexdigest()
            newitem.lastAccessed    = datetime.now()
            newitem.put()
        else:
            #if they do, only modify the card number
            for response in Card.all().filter("username =",self.user_name):
                response.hashedCard     = m.hexdigest()
                response.lastAccessed   = datetime.now()
                response.put()

        self.redirect('/')

class Validate(webapp.RequestHandler):
    def post(self):
        self.token = self.request.get("token")
        if self.token == SECRET_TOKEN:
            self.rfid = self.request.get("rfid")
            
            # newer rfid clients will set the resource value
            # older clients didn't set this value, so force it to "allowed" and set a legacy flag
            # to only return simplified results
            self.legacy = False
            self.resource = self.request.get("resource")
            if self.resource == "":
               self.legacy = True
               self.resource = "allowed"

            m = hashlib.sha224()
            m.update(str(self.rfid))

            user = Card.all().filter("hashedCard =",m.hexdigest())
            if user.count() <=0:
                username = None
                result = 'denied'
            else:
                username = user[0].username
                if self.legacy:
                   # legacy mode which only will return 'allowed' or 'denied'
                   if 'allowed' in user[0].allowed:
                      result = 'allowed'
                   else:
                      result = 'denied'
                else:
                   # modern mode which will return a comma-delimited permissions string
                   result = user[0].allowed

            logEntry = AccessLog()
            logEntry.timestamp 	= datetime.now()
            logEntry.rfidhash 	= m.hexdigest()
            logEntry.username	= username
            logEntry.result 	= result
            logEntry.resource   = self.resource
            logEntry.put()

            output = simplejson.dumps({'key':m.hexdigest(),'username':str(username),'allowed':result})
            self.response.out.write(output)

class DumpKeys(webapp.RequestHandler):
    def post(self):
        self.token = self.request.get("token")
        if self.token == SECRET_TOKEN:
            cards = Card.all()
            output = ""
            for card in cards:
                card.username.nickname = " ".join([s.capitalize() for s in str(card.username).split(".")])
                output += '%s,%s,%s\n'%(card.hashedCard,card.username.nickname,card.allowed)
                self.response.out.write(output)
        else:
			self.response.out.write('token denied')

class Log(webapp.RequestHandler):

    def get(self):
        #authenticates user
        self.user_name = users.get_current_user()
        if not self.user_name:
            self.redirect(users.create_login_url(self.request.uri))

        #retrieves the access log
        log = AccessLog.all().order('-timestamp').fetch(limit=250)
        for l in log:
            #Tell the time it is in UTC
            utc = l.timestamp.replace(tzinfo=UTC())
            #Make it convert to EST/EDT
            l.timestamp = utc.astimezone(EasternTZ())
            #Format user names to First Last instead of first.last
            if l.username == None:
                l.nickname = 'Unknown User'
            else:
                l.nickname = " ".join([s.capitalize() for s in str(l.username).split(".")])

            # workaround for old entries which didn't have a resource
            if l.resource == None:
               l.resource = 'allowed'
            
            # get a friendly looking resource name from the dict
            if l.resource in RESOURCES:
               l.resourcedesc = RESOURCES[l.resource]
            else:
               l.resourcedesc = l.resource

            if resourceIsAllowed(l.resource, l.result):
               l.allowed = "Yes"
            else:
               l.allowed = "No"

        self.response.out.write(template.render('templates/log.html', locals()))

class AdminPanel(webapp.RequestHandler):
    def get(self):

       if adminCheck(self):
          
          cards = Card.all().fetch(limit=9999)
          for card in cards:
             if card.lastAccessed:
                utc = card.lastAccessed.replace(tzinfo=UTC())
                # convert to EST/EDT
                card.lastAccessed = utc.astimezone(EasternTZ())
             # Format user names to First Last instead of first.last
             card.nickname = " ".join([s.capitalize() for s in str(card.username).split(".")])

             # on the admin screen, allow quick editing of just the 'allowed' permission
             card.access = resourceIsAllowed('allowed', card.allowed)

             # build a dictionary of all available resources and bools for whether access is allowed
             #card.permissions = dict()
             #for res in RESOURCES:
             #   desc = RESOURCES[res]
             #   card.permissions[desc] = resourceIsAllowed(res, card.allowed)

          cards = sorted(cards,key=attrgetter('nickname'))

          self.response.out.write(template.render('templates/adminpanel.html', locals()))
        
       else:
          pass

#    def post(self):
#       # retrieve the card holders
#       cards = Card.all()
#       for card in cards:
#          try:
#             newAllowed = bool(self.request.get('allowed_%s'%(card.username)) == "true")
#             
#             if newAllowed != resourceIsAllowed('allowed', card.allowed):
#                # access has changed
#                
#                permissions = ''
#                for res in RESOURCES:
#                   if permissions != '':
#                      permissions += ','
#                   if res == 'allowed':
#                      if newAllowed:
#                         permissions += 'allowed'
#                      else:
#                         permissions += 'denied'
#                   else:
#                      if resourceIsAllowed(res, card.allowed):
#                         permissions += res
#
#                #card.allowed = permissions
#                #card.put()
#
#                self.response.out.write(card.username + " = " + permissions)
#          except:
#             pass
#       #self.redirect('/admin')

class UserProfile(webapp.RequestHandler):
   def get(self, username):

      if adminCheck(self):
         for card in Card.all().filter("username =", users.User(username+domain)):
            try:
               nickname = " ".join([s.capitalize() for s in str(card.username).split(".")])
               email = username + domain

               # build a dictionary of all available resources and bools for whether access is allowed
               permissions = dict()
               for res in RESOURCES:
                  permissions[res] = resourceIsAllowed(res, card.allowed)

            except:
               pass

            # retrieves the access log
            log = AccessLog.all().filter("username =", users.User(username+domain)).order('-timestamp').fetch(limit=250)
            for l in log:
               # Tell the time it is in UTC
               utc = l.timestamp.replace(tzinfo=UTC())
               # Make it convert to EST/EDT
               l.timestamp = utc.astimezone(EasternTZ())

               # workaround for old entries which didn't have a resource
               if l.resource == None:
                  l.resource = 'allowed'
            
               # get a friendly looking resource name from the dict
               if l.resource in RESOURCES:
                  l.resourcedesc = RESOURCES[l.resource]
               else:
                  l.resourcedesc = l.resource

               if resourceIsAllowed(l.resource, l.result):
                  l.allowed = "Yes"
               else:
                  l.allowed = "No"

         self.response.out.write(template.render('templates/user.html', locals()))

      else:
         pass

   def post(self,username):
      try: 
         if adminCheck(self):
            
            permissions = ''
            for res in RESOURCES:
               if bool(self.request.get('perm_' + res) == 'true'):
                  if permissions != '':
                     permissions += ','
                  permissions += res

            for card in Card.all().filter("username =", users.User(username+domain)):
               card.allowed = permissions
               card.lastAccessed = datetime.now()
               card.put()

            self.redirect('/user/' + username)

         else:
            pass
                
      except:
         self.redirect('/admin')




########################

application = webapp.WSGIApplication([('/', MainPage),
                                      ('/newcard', NewCard),
                                      ('/validate', Validate),
                                      ('/dumpKeys', DumpKeys),
                                      ('/admin', AdminPanel),
                                      ('/log', Log),
                                      (r'/user/(.+)',UserProfile)
                                     ],
                                     debug=True)


def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
