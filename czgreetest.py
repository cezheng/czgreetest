import jinja2
import os,sys

jinja_environment = jinja2.Environment(
                loader = jinja2.FileSystemLoader(os.path.dirname(__file__)))

import cgi
import datetime
import urllib
import webapp2

import logging

from google.appengine.ext import db

import oauth
import urllib2
import json
import ConfigParser
import oauth.oauth as oauth

GREE_EVENT_PARAMS = {
                'event.addapp':['eventtype','opensocial_app_id','id','invite_from_id','user_hash'],
                'event.suspendapp':['eventtype','opensocial_app_id','id'],
                'event.resumeapp':['eventtype','opensocial_app_id','id'],
                'event.removeapp':['eventtype','opensocial_app_id','id'],
                'gree.join_community':['eventtype','opensocial_app_id','id','community_id','acted_time'],
                'gree.leave_community':['eventtype','opensocial_app_id','id','community_id','acted_time'],
                }

INT_PARAMS = set(['opensocial_app_id','id','invite_from_id'])

REQUIRED_PARAMS = set(['oauth_version','oauth_nonce','oauth_timestamp','oauth_consumer_key','oauth_token','oauth_signature_method']) 

OAUTH_CONFIG_FILE = 'gree_oauth.ini'


class Event(db.Model):
        eventtype = db.StringProperty()
        opensocial_app_id = db.IntegerProperty()
        id = db.IntegerProperty()
        invite_from_id = db.IntegerProperty()
        user_hash = db.StringProperty()
        community_id = db.IntegerProperty()
        acted_time = db.StringProperty()
        date = db.DateTimeProperty(auto_now_add = True)

def records_key():
        return db.Key.from_path('Event', 'default')

class APICaller(object):
        def __init__(self,http_url,http_method='GET',parameters=None):
                self.http_url = http_url
                self.http_method = http_method
                self.parameters = parameters
        def get_conf(self):
                p = ConfigParser.ConfigParser()
                p.read(OAUTH_CONFIG_FILE)
                return p
        def call_api(self):
                OAUTH_CONFIG_FILE = 'gree_oauth.ini'
                app_conf = self.get_conf()
                oauth_conf = dict(app_conf.items('oauth'))
                # parse user request
                user_request = oauth.OAuthRequest.from_request(self.http_method,self.http_url, parameters=self.parameters)
                oauth_token = user_request.get_parameter('oauth_token')
                oauth_token_secret = user_request.get_parameter('oauth_token_secret')
                oauth_signature = user_request.get_parameter('oauth_signature')
                opensocial_viewer_id = user_request.get_parameter('opensocial_viewer_id')
                xoauth_requestor_id = opensocial_viewer_id
                # api endpoint
                endpoint_url = oauth_conf['api.endpoint_url'] + '/people/@me/@self'
                http_method = 'GET'
                # url query
                request_data = dict([(k,self.parameters[k]) for k in REQUIRED_PARAMS])
                request_data['xoauth_requestor_id'] = xoauth_requestor_id
                # sign request
                signature_method = oauth.OAuthSignatureMethod_HMAC_SHA1()
                oauth_consumer = oauth.OAuthConsumer(oauth_conf['consumer_key'], oauth_conf['consumer_secret'])
                access_token   = oauth.OAuthToken(oauth_token,oauth_token_secret)
                oauth_request = oauth.OAuthRequest.from_consumer_and_token(
                               oauth_consumer = oauth_consumer, 
                               token = access_token, 
                               http_method = http_method, 
                               http_url = endpoint_url, 
                               parameters = request_data
                               )
                oauth_request.sign_request(signature_method, oauth_consumer, access_token)

                # get header
                authorization_header_dict = oauth_request.to_header()
                authorization_header = authorization_header_dict['Authorization'].replace('realm="", ','').replace(', ',',') + ',xoauth_requestor_id="' + request_data['xoauth_requestor_id'] + '"'

                # build api request
                http_request = urllib2.Request(endpoint_url)
                http_request.add_header('Content-Type', "application/json")
                http_request.add_header('Authorization', authorization_header)
                # logging
                logging.info(http_request.get_method() + ' url: ' + endpoint_url + ' ; Authorization: ' + authorization_header)
                # send api request
                try:
                        request_result = urllib2.urlopen(http_request,timeout=10)
                except urllib2.HTTPError,e:
                        logging.info(str(e) + ' ' + e.read())
                        raise e

                # get api result
                response_code = request_result.getcode()
                response_body = json.loads(request_result.read())
                return (response_code,response_body)

class MainPage(webapp2.RequestHandler):
        def get(self):
                properties = Event.properties()
                record_query = Event.all().ancestor(records_key()).order('-date')
                records = record_query.fetch(30)

                # call GREE API
                http_url = self.request.host + self.request.path
                http_method = self.request.method
                parameters = dict(self.request.GET)
                api_caller = APICaller(http_url,http_method,parameters)
                try:
                        (response_code,response_body) = api_caller.call_api()
                        api_success = True
                except Exception,e:
                        api_success = False
                        error = e
                template_values = {
                                'user_profile': response_body,
                                'properties': properties,
                                'records': records,
                                }

                template = jinja_environment.get_template('index.html')
                self.response.out.write(template.render(template_values))

class EventHandler(webapp2.RequestHandler):
        def get(self):
                params = {}
                eventtype = params['eventtype'] = self.request.get('eventtype')
                if eventtype not in GREE_EVENT_PARAMS:
                        self.response.out.write('failure')
                        return
                for key in GREE_EVENT_PARAMS[eventtype]:
                        value = self.request.get(key)
                        if len(value)==0:
                                if key in ('id','opensocial_app_id'):
                                        self.response.out.write('failure')
                                        return
                                continue
                        params[key] = value
                        if key in INT_PARAMS:
                                params[key]=int(params[key])
                event = Event(parent = records_key(),**params)
                result = event.put()
                self.response.out.write('success')

app = webapp2.WSGIApplication([('/', MainPage),
        ('/event/[^/]+', EventHandler)],
                              debug = True)
