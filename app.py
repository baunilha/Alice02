# --------- Import Libraries ----------------------------------------------------

# -*- coding: utf-8 -*-
import os, datetime, re, sys
from flask import Flask, session, request, url_for, escape, render_template, json, jsonify, flash, redirect, abort
from werkzeug import secure_filename
from unidecode import unidecode

# import all of mongoengine
from flask.ext.mongoengine import mongoengine

# Flask-Login 
from flask.ext.login import (LoginManager, current_user, login_required,
                            login_user, logout_user, UserMixin, AnonymousUser,
                            confirm_login, fresh_login_required)

# Library
from flaskext.bcrypt import Bcrypt

#custom user library - maps User object to User model
from libs.user import *

# import data models
import models

# Amazon AWS library
import boto

# Python Image Library
import StringIO


# --------- Config ----------------------------------------------------

app = Flask(__name__)   # create our flask app
app.debug = True
app.secret_key = os.environ.get('SECRET_KEY') # put SECRET_KEY variable inside .env file with a random string of alphanumeric characters
app.config['CSRF_ENABLED'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 megabyte file upload

# Flask BCrypt will be used to salt the user password
flask_bcrypt = Bcrypt(app)

# --------- Database Connection ----------------------------------------------------


# MongoDB connection to MongoLab's database
# uses .env file to get connection string
# using a remote db get connection string from heroku config
# 	using a local mongodb put this in .env
#   MONGOLAB_URI=mongodb://localhost:27017/dwdfall2012
mongoengine.connect('userdemo', host=os.environ.get('MONGOLAB_URI'))
app.logger.debug("Connecting to MongoLabs")

# Login management defined
# reference http://packages.python.org/Flask-Login/#configuring-your-application
login_manager = LoginManager()
login_manager.anonymous_user = Anonymous
login_manager.login_view = "login"
login_manager.login_message = u"Please log in to access this page."
login_manager.refresh_view = "reauth"

# Flask-Login requires a 'user_loader' callback 
# This method will called with each Flask route request automatically
# When this callback runs, it will populate the User object, current_user
# reference http://packages.python.org/Flask-Login/#how-it-works
@login_manager.user_loader
def load_user(id):
	if id is None:
		redirect('/login')

	user = User()
	user.get_by_id(id)
	if user.is_active():
		return user
	else:
		return None

# connect the login manager to the main Flask app
login_manager.setup_app(app)


ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])



# --------- Lists ----------------------------------------------------

# Create the lists that match the name of the ListField in the models.py
period = ['Morning', 'Afternoon', 'Night']
interest = ['Fun with Friends', "Let's Party!", 'Show Time', 'Relax', 'Sips and Nibs', 'Flea Market', 'Munch', 'Special Eats', 'Unusual Edibles', 'City Secrets', 'Wonder Around', 'Learn Something']
mood = ['Zippy', 'Chill', 'Hungry', 'Curious']

# Create the lists for LOCATIONS that match the name of the ListField in the models.py
city = ['New York', 'San Francisco']
price = ['$','$$','$$$','$$$$','$$$$$']


# --------- Main Page, Add, View and Delete Experiences  -----------------------------------------------------------

# This is the main page
@app.route("/", methods=["GET", "POST"])
@login_required
def index():

	# get existing experiences
	experience = models.Experience.objects.order_by('-timestamp')

	# prepare the template data dictionary
	templateData = {
		'experiences': models.Experience.objects(),
		'current_user' : current_user,
		'experience': experience,
		'users' : models.User.objects()
	}

	app.logger.debug(current_user)

	# render the template, retrieve 'experiences' from the database
	return render_template("03mood.html", **templateData)



# this is the submit experiences page
@app.route("/submit", methods=['GET','POST'])
def submit():

	# get Experience form from models.py
	photo_upload_form = models.photo_upload_form(request.form)

	# get created lists
	app.logger.debug(request.form.getlist('interest'))
	app.logger.debug(request.form.getlist('mood'))
	app.logger.debug(request.form.getlist('period'))
	
	# if form was submitted and it is valid...
	if request.method == "POST" and photo_upload_form.validate():
		
		uploaded_file = request.files['fileupload']
		
		# Uploading is fun
		# 1 - Generate a file name with the datetime prefixing filename
		# 2 - Connect to s3
		# 3 - Get the s3 bucket, put the file
		# 4 - After saving to s3, save data to database

		if uploaded_file and allowed_file(uploaded_file.filename):
			# create filename, prefixed with datetime
			now = datetime.datetime.now()
			filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)
			# thumb_filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)

			# connect to s3
			s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

			# open s3 bucket, create new Key/file
			# set the mimetype, content and access control
			b = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
			k = b.new_key(b)
			k.key = filename
			k.set_metadata("Content-Type", uploaded_file.mimetype)
			k.set_contents_from_string(uploaded_file.stream.read())
			k.make_public()

			# save information to MONGO database
			# did something actually save to S3
			if k and k.size > 0:
				
				experience = models.Experience()
				experience.title = request.form.get('title')
				experience.slug = slugify(experience.title)
				experience.interest = request.form.getlist('interest')
				experience.mood = request.form.getlist('mood')
				experience.period = request.form.getlist('period')
				experience.description = request.form.get('description')
				experience.postedby = request.form.get('postedby')
				experience.filename = filename # same filename of s3 bucket file
				experience.save()

			return redirect('/submit')

		else:
			return "uhoh there was an error " + uploaded_file.filename

	else:
		# get existing experiences
		experiences = models.Experience.objects.order_by('-timestamp')

		if request.form.getlist('interest'):
			for i in request.form.getlist('interest'):
				photo_upload_form.interest.append_entry(i)

		if request.form.getlist('mood'):
			for m in request.form.getlist('mood'):
				photo_upload_form.mood.append_entry(m)

		if request.form.getlist('period'):
			for p in request.form.getlist('period'):
				photo_upload_form.period.append_entry(p)
		
		# render the template
		templateData = {
			'experiences' : experiences,
			'interest' : interest,
			'mood': mood,
			'period': period,
			'form' : photo_upload_form
		}

		return render_template("submit.html", **templateData)


# pages for all experiences
@app.route("/experiences")
def experiences():
	# render the template, retrieve 'experiences' from the database
	return render_template("experiences.html", experiences=models.Experience.objects())


# pages for individual experiences
@app.route("/experiences/<experience_slug>")
def experience_display(experience_slug):

	# get experience by experience_slug
	try:
		experience = models.Experience.objects.get(slug=experience_slug)
	except:
		abort(404)

	# prepare template data
	templateData = {
		'experience' : experience
	}

	# render and return the template
	return render_template('06experience_entry.html', **templateData)


@app.route('/experiences/delete/<experience_id>')
def delete_experience(experience_id):
	
	experience = models.Experience.objects.get(id=experience_id)
	if experience:

		# delete from s3
	
		# connect to s3
		s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

		# open s3 bucket, create new Key/file
		# set the mimetype, content and access control
		bucket = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
		k = bucket.new_key(bucket)
		k.key = experience.filename
		bucket.delete_key(k)

		# delete from Mongo	
		experience.delete()

		return redirect('/submit')

	else:
		return "Unable to find requested image in database."




# --------- Locations ----------------------------------------------------

# the form to submit
# add location to experiences form 
@app.route("/experiences/<experience_slug>/location", methods=['GET', 'POST'])
def add_location(experience_slug):

	# get Location form from models.py based on the photo
	photo_upload_location = models.photo_upload_location(request.form)

	# get experience by experience_slug
	experience = models.Experience.objects.get(slug=experience_slug)


	# if form was submitted and it is valid...
	if request.method == "POST" and photo_upload_location.validate():
		
		uploaded_file = request.files['photoupload']
		
		# Uploading is fun
		# 1 - Generate a file name with the datetime prefixing filename
		# 2 - Connect to s3
		# 3 - Get the s3 bucket, put the file
		# 4 - After saving to s3, save data to database

		if uploaded_file and allowed_file(uploaded_file.filename):
			# create filename, prefixed with datetime
			now = datetime.datetime.now()
			filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)
			# thumb_filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)

			# connect to s3
			s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

			# open s3 bucket, create new Key/file
			# set the mimetype, content and access control
			b = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
			k = b.new_key(b)
			k.key = filename
			k.set_metadata("Content-Type", uploaded_file.mimetype)
			k.set_contents_from_string(uploaded_file.stream.read())
			k.make_public()

			# save information to MONGO database
			# did something actually save to S3
			if k and k.size > 0:

				# create a location
				location = models.Location()
				location.name = request.form.get('name')
				location.slug = slugify(location.name)
				location.description = request.form.get('description')
				location.address = request.form.get('address')
				location.neighborhood = request.form.get('neighborhood')
				location.city = request.form.get('city')
				location.price = request.form.get('price')
				location.website = request.form.get('website')
				location.phone = request.form.get('phone')
				location.filename = filename # same filename of s3 bucket file				

				try:
					# for reference field, save the location
					location.save() # saves a separate Location document (not embedded)

					# append location to experience
					experience.location_refs.append(location)

					# save the experience object
					experience.save()

				except:
					e = sys.exc_info()
					app.logger.error(e)

			return redirect('/experiences/%s' % experience.slug)

		else:
			return "uhoh there was an error with the picture " + uploaded_file.filename

	else:

		# get experience by experience_slug
		experience = models.Experience.objects.get(slug=experience_slug)

		# prepare template data
		templateData = {
			'experience' : experience,
			'form' : photo_upload_location
		}

		# render and return the template
		return render_template('experience_entry.html', **templateData)



# location page
@app.route("/location/<location_slug>")
def location(location_slug):

# 	# get location by location_slug
	try:
		location = models.Location.objects.get(slug=location_slug)
	except:
		abort(404)

	# prepare template data
	templateData = {
		'location' : location,
		'address_map' : location.address.replace(' ','+'),
		'neighborhood_map' : location.neighborhood.replace(' ','+'),
		'city_map' : location.city.replace(' ','+')
	}

	# render and return the template
	return render_template('07location_entry.html', **templateData)



# --------- Interests and Mood ----------------------------------------------------


# Display all experiences for a specific category
@app.route("/interest/<int_name>")
def by_interest(int_name):

	# try and get experiences where int_name is inside the interest list
	try:
		experiences = models.Experience.objects(interest=int_name).limit(5)

	# not found, abort w/ 404 page
	except:
		abort(404)

	# prepare data for template
	templateData = {
		'current_interest' : {
			'slug' : int_name,
			'name' : int_name.replace('_',' ')
		},
		'experiences' : experiences,
		'interest' : interest
	}

	# render and return template
	return render_template('05interest_listing.html', **templateData)


# Display categories by mood
@app.route("/mood/<mood_name>")
def by_mood(mood_name):

	# try and get experiences where mood_name is inside the mood list
	try:
		experiences = models.Experience.objects(mood=mood_name)

	# not found, abort w/ 404 page
	except:
		abort(404)

	# prepare data for template
	templateData = {
		'current_mood' : {
			'slug' : mood_name,
			'name' : mood_name.replace('_',' ')
		},
		'experiences' : experiences,
		'mood' : mood,
		'interest' : interest
	}

	if mood_name == "Zippy":

		# Separate the first interest and make it the active div on the carousel
		firstInterest = ['Fun_with_Friends']
		firstinterestExperiences = []

		# loop through interest
		for firstInt in firstInterest:
			exp_from_db = models.Experience.objects(interest=firstInt).order_by('-timestamp').first()
			firstinterestExperiences.append( exp_from_db )
		
		templateData['firstinterestExperiences'] = firstinterestExperiences

		# get the other 2 interests that are left from this mood and show the last entry on the carousel
		tmpInterests = ["Let's_Party!", 'Show_Time']
		interestExperiences = []
		
		# loop through interest
		for tmpInt in tmpInterests:
			exp_from_db = models.Experience.objects(interest=tmpInt).order_by('-timestamp').first()
			interestExperiences.append( exp_from_db )
		
		templateData['interestExperiences'] = interestExperiences

		# render and return template
		return render_template('04mood_listing01.html', **templateData)

	if mood_name == "Chill":

		# Separate the first interest and make it the active div on the carousel
		firstInterest = ['Relax']
		firstinterestExperiences = []

		# loop through interest
		for firstInt in firstInterest:
			exp_from_db = models.Experience.objects(interest=firstInt).order_by('-timestamp').first()
			firstinterestExperiences.append( exp_from_db )
		
		templateData['firstinterestExperiences'] = firstinterestExperiences

		# get the other 2 interests that are left from this mood and show the last entry on the carousel
		tmpInterests = ['Sips_and_Nibs', 'Flea_Market']
		interestExperiences = []
		
		# loop through intereste
		for tmpInt in tmpInterests:
			exp_from_db = models.Experience.objects(interest=tmpInt).order_by('-timestamp').first()
			interestExperiences.append( exp_from_db )
		
		templateData['interestExperiences'] = interestExperiences


		return render_template('04mood_listing02.html', **templateData)

	if mood_name == "Hungry":

		# Separate the first interest and make it the active div on the carousel
		firstInterest = ['Munch']
		firstinterestExperiences = []

		# loop through interest
		for firstInt in firstInterest:
			exp_from_db = models.Experience.objects(interest=firstInt).order_by('-timestamp').first()
			firstinterestExperiences.append( exp_from_db )
		
		templateData['firstinterestExperiences'] = firstinterestExperiences

		# get the other 2 interests that are left from this mood and show the last entry on the carousel
		tmpInterests = ['Special_Eats', 'Unusual_Edibles']
		interestExperiences = []
		
		# loop through intereste
		for tmpInt in tmpInterests:
			exp_from_db = models.Experience.objects(interest=tmpInt).order_by('-timestamp').first()
			interestExperiences.append( exp_from_db )

		# app.logger.info(interestExperiences[1].title)

		templateData['interestExperiences'] = interestExperiences

		return render_template('04mood_listing03.html', **templateData)

	else: 

		# Separate the first interest and make it the active div on the carousel
		firstInterest = ['City_Secrets']
		firstinterestExperiences = []

		# loop through interest
		for firstInt in firstInterest:
			exp_from_db = models.Experience.objects(interest=firstInt).order_by('-timestamp').first()
			firstinterestExperiences.append( exp_from_db )
		
		templateData['firstinterestExperiences'] = firstinterestExperiences

		# get the other 2 interests that are left from this mood and show the last entry on the carousel
		tmpInterests = ['Wonder_Around', 'Learn_Something']
		interestExperiences = []
		
		# loop through intereste
		for tmpInt in tmpInterests:
			exp_from_db = models.Experience.objects(interest=tmpInt).order_by('-timestamp').first()
			interestExperiences.append( exp_from_db )
		
		templateData['interestExperiences'] = interestExperiences

		return render_template('04mood_listing04.html', **templateData)




# --------- Search Pages!!!!  --------------------------------------------------------------------------


# Search Experiences
@app.route("/search", methods=['POST'])
def search():

	# Create an empty string for the searched experiences
	search_experiences = []
	# Get the searched string from the website and store it in a new variable
	search_str = request.form.get('search')

	# Compare the searched string in the website with the titles of the experiences
	search_display = models.Experience.objects()
	search_display = models.Experience.objects(title__icontains=search_str)

	# for all the results, append them in the website
	for s in search_display:
		search_experiences.append(s)

	templateData = {
		'experiences' : search_experiences,
		'search_str' : search_str
	}

	return render_template("12search.html", **templateData)


# Search Lists
@app.route("/slist", methods=['POST'])
def slist():

	# Create an empty string for the searched lists
	search_list = []
	# Get the searched string from the website and store it in a new variable
	search_str = request.form.get('search')

	# Compare the searched string in the website with the descriptions of the lists
	search_display = models.List.objects()
	search_display = models.List.objects(listDescription__icontains=search_str)

	# for all the results, append them in the website
	for s in search_display:
		search_list.append(s)

	templateData = {
		'listsCreated' : search_list,
		'search_str' : search_str
	}

	return render_template("13search_list.html", **templateData)


# --------- Create a new List  --------------------------------------------------------------------------


# To create a new list
@app.route("/create", methods=['GET','POST'])
@login_required
def create():

	# get List form from models.py based on the photo
	photo_upload_list = models.photo_upload_list(request.form)

	
	# if form was submitted and it is valid...
	if request.method == "POST" and photo_upload_list.validate():
		
		uploaded_file = request.files['photoupload']
		
		# Uploading is fun
		# 1 - Generate a file name with the datetime prefixing filename
		# 2 - Connect to s3
		# 3 - Get the s3 bucket, put the file
		# 4 - After saving to s3, save data to database

		if uploaded_file and allowed_file(uploaded_file.filename):
			# create filename, prefixed with datetime
			now = datetime.datetime.now()
			filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)
			# thumb_filename = now.strftime('%Y%m%d%H%M%s') + "-" + secure_filename(uploaded_file.filename)

			# connect to s3
			s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

			# open s3 bucket, create new Key/file
			# set the mimetype, content and access control
			b = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
			k = b.new_key(b)
			k.key = filename
			k.set_metadata("Content-Type", uploaded_file.mimetype)
			k.set_contents_from_string(uploaded_file.stream.read())
			k.make_public()

			# save information to MONGO database
			# did something actually save to S3
			if k and k.size > 0:
				
				createList = models.List()
				createList.listName = request.form.get('listName')
				createList.slug = slugify(createList.listName)
				createList.listDescription = request.form.get('listDescription')
				createList.postedby = request.form.get('postedby')
				createList.filename = filename # same filename of s3 bucket file
				#link to current user
				createList.user = current_user.get()

				try:
					createList.save()

				except:
					e = sys.exc_info()
					app.logger.error(e)
				

			return redirect('/create')

		else:
			return "uhoh there was an error " + uploaded_file.filename

	else:
		# get existing listsCreated
		listsCreated = models.List.objects.order_by('timestamp')
		
		# render the template
		templateData = {
			'current_user' : current_user,
			'users' : models.User.objects(),
			'listsCreated' : listsCreated,
			'form' : photo_upload_list
		}

		app.logger.debug(current_user)

		return render_template("09create_list.html", **templateData)


# pages for all lists
@app.route("/lists")
def lists():
	# render the template, retrieve 'lists' from the database
	return render_template("lists.html", listsCreated=models.List.objects())


# pages for lists
@app.route("/lists/<list_slug>")
def list_display(list_slug):
	
	# get lists by list_slug
	try:
		listsCreated = models.List.objects.get(slug=list_slug)
	except:
		abort(404)

	# prepare template data
	templateData = {
		'listsCreated' : listsCreated,
		'experiences': models.Experience.objects()
	}

	# render and return the template
	return render_template('11list_entry.html', **templateData)


# not working
# Display all the lists for a given user.
@app.route('/lists/<user_name>')
def user_list(user_name):

	templateData = {
		'user_now' : models.User.objects(username=user_name),
		'user_name' : user_name,
		'allLists' : models.List.objects(user=user_name),
		'current_user' : current_user,
		'experiences': models.Experience.objects()
	}

	return render_template('lists_user.html', **templateData)


# To delete a List
@app.route('/lists/delete/<list_id>')
def delete_list(list_id):
	
	listsCreated = models.List.objects.get(id=list_id)
	if listsCreated:

		# delete from s3
	
		# connect to s3
		s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

		# open s3 bucket, create new Key/file
		# set the mimetype, content and access control
		bucket = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
		k = bucket.new_key(bucket)
		k.key = listsCreated.filename
		bucket.delete_key(k)

		# delete from Mongo	
		listsCreated.delete()

		return redirect('/create')

	else:
		return "Unable to find requested image in database."



# Choose a list from the user to put the experience in
@app.route('/chooselist/<experience_id>')
@login_required
def choose_list(experience_id):

	# get experience by experience_slug
	try:
		experience = models.Experience.objects.get(id=experience_id)
	except:
		# error, return to where you came from
		return redirect(request.referrer)

	templateData = {
		'allLists' : models.List.objects(user=current_user.id),
		'current_user' : current_user,
		'experience' : experience
	}

	return render_template('08choose_list.html', **templateData)



# save an experience in a list
@app.route("/list/<list_id>/add/<experience_id>", methods=['GET','POST'])
def list_add_experience(list_id, experience_id):

	# get experience by experience_slug
	try:
		experience = models.Experience.objects.get(id=experience_id)
	except:
		# error, return to where you came from
		return redirect(request.referrer)


	# get list by experience_slug
	try:
		listsCreated = models.List.objects.get(id=list_id)
	except:
		# error, return to where you came from
		return redirect(request.referrer)

	listsCreated.experiences.append( experience )
	listsCreated.save()

	return redirect('/lists/' + listsCreated.slug)



# --------- Login & Register -------------------------------------------------------------------------


# this is the login page
@app.route("/login", methods=["GET", "POST"])
def login():

	# get the login and registration forms
	loginForm = models.LoginForm(request.form)
	
	# is user trying to log in?
	# 
	if request.method == "POST" and 'email' in request.form:
		email = request.form["email"]

		user = User().get_by_email_w_password(email)
		
		# if user in database and password hash match then log in.
	  	if user and flask_bcrypt.check_password_hash(user.password,request.form["password"]) and user.is_active():
			remember = request.form.get("remember", "no") == "yes"

			if login_user(user, remember=remember):
				flash("Logged in!")
				return redirect(request.args.get("next") or '/')
			else:

				flash("unable to log you in","login")
	
		else:
			flash("Incorrect email and password submission","login")
			return redirect("/login")

	else:

		templateData = {
			'form' : loginForm
		}

		return render_template('/01login.html', **templateData)


#
# Register new user
#
@app.route("/register", methods=['GET','POST'])
def register():
	
	# prepare registration form 
	registerForm = models.SignupForm(request.form)
	app.logger.info(request.form)

	if request.method == 'POST' and registerForm.validate():
		email = request.form['email']
		username = request.form['username']

		# generate password hash
		password_hash = flask_bcrypt.generate_password_hash(request.form['password'])
		
		# prepare User
		user = User(username=username, email=email, password=password_hash)
		
		# save new user, but there might be exceptions (uniqueness of email and/or username)
		try:
			user.save()	
			if login_user(user, remember="no"):
				flash("Logged in!")
				return redirect(request.args.get("next") or '/')
			else:
				flash("unable to log you in")

		# got an error, most likely a uniqueness error
		except mongoengine.queryset.NotUniqueError:
			e = sys.exc_info()
			exception, error, obj = e
			
			app.logger.error(e)
			app.logger.error(error)
			app.logger.error(type(error))

			# uniqueness error was raised. tell user (via flash messaging) which error they need to fix.
			if str(error).find("email") > -1:			
				flash("Email submitted is already registered.","register")
	
			elif str(error).find("username") > -1:
				flash("Username is already registered. Pick another.","register")

			app.logger.error(error)	

	# prepare registration form			
	templateData = {
		'form' : registerForm
	}
	
	return render_template("/02register.html", **templateData)


# User profile page
@app.route('/admin')
@login_required
def admin_main():

	# get existing listsCreated
	listsCreated = models.List.objects.order_by('timestamp')

	templateData = {
		'allLists' : models.List.objects(user=current_user.id),
		'listsCreated' : listsCreated,
		'current_user' : current_user,
		'experiences': models.Experience.objects()
	}

	return render_template('10admin.html', **templateData)



@app.route("/reauth", methods=["GET", "POST"])
@login_required
def reauth():
    if request.method == "POST":
        confirm_login()
        flash(u"Reauthenticated.")
        return redirect(request.args.get("next") or url_for("index"))
    
    templateData = {}
    return render_template("/auth/reauth.html", **templateData)


@app.route("/logout")
@login_required
def logout():
	logout_user()
	flash("Logged out.")
	return redirect("/login")



# --------- Additional Basic Pages ------------------------------------------------------------------


def datetimeformat(value, format='%H:%M / %d-%m-%Y'):
	return value.strftime(format)

@app.errorhandler(404)
def page_not_found(error):
	return render_template('404.html'), 404

def allowed_file(filename):
	return '.' in filename and \
		filename.lower().rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

# slugify the title 
# via http://flask.pocoo.org/snippets/5/
_punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.]+')
def slugify(text, delim=u'-'):
	"""Generates an ASCII-only slug."""
	result = []
	for word in _punct_re.split(text.lower()):
		result.extend(unidecode(word).split())
	return unicode(delim.join(result))




# --------- Server On ----------------------------------------------------------------------------------

# start the webserver
if __name__ == "__main__":
	app.debug = True
	
	port = int(os.environ.get('PORT', 5000)) # locally PORT 5000, Heroku will assign its own port
	app.run(host='0.0.0.0', port=port)





# --------- Not using! ----------------------------------------------------------------------------------

# Login route - will display login form and receive POST to authenicate a user
# Not being used!!!
@app.route("/login", methods=["GET", "POST"])
def login():

	# get the login and registration forms
	loginForm = models.LoginForm(request.form)
	
	# is user trying to log in?
	# 
	if request.method == "POST" and 'email' in request.form:
		email = request.form["email"]

		user = User().get_by_email_w_password(email)
		
		# if user in database and password hash match then log in.
	  	if user and flask_bcrypt.check_password_hash(user.password,request.form["password"]) and user.is_active():
			remember = request.form.get("remember", "no") == "yes"

			if login_user(user, remember=remember):
				flash("Logged in!")
				return redirect(request.args.get("next") or '/admin')
			else:

				flash("unable to log you in","login")
	
		else:
			flash("Incorrect email and password submission","login")
			return redirect("/login")

	else:

		templateData = {
			'form' : loginForm
		}

		return render_template('/auth/login.html', **templateData)






	