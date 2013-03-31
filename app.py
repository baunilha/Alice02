# --------- Import Libraries ----------------------------------------------------

# -*- coding: utf-8 -*-
import os, datetime, re
from flask import Flask, request, render_template, redirect, abort
from werkzeug import secure_filename
from unidecode import unidecode

# import all of mongoengine
from flask.ext.mongoengine import mongoengine

# import data models
import models

# Amazon AWS library
import boto

# Python Image Library
import StringIO


# --------- Config ----------------------------------------------------

app = Flask(__name__)   # create our flask app
app.secret_key = os.environ.get('SECRET_KEY') # put SECRET_KEY variable inside .env file with a random string of alphanumeric characters
app.config['CSRF_ENABLED'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 megabyte file upload


# --------- Database Connection ----------------------------------------------------

# MongoDB connection to MongoLab's database
mongoengine.connect('mydata', host=os.environ.get('MONGOLAB_URI'))
app.logger.debug("Connecting to MongoLabs")

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])


# --------- Lists ----------------------------------------------------

# Create the lists that match the name of the ListField in the models.py
period = ['Morning', 'Afternoon', 'Night']
interest = ['Brunch Place', 'City Secrets', 'Cool & Cheap', 'Date Spots', 'Exploring NYC', 'Fun with Friends', 'I need Coffee!', 'Learn Something', "Let's Party!", 'Lifetime Experiences', 'Ready for Adventure', 'Special Eats', 'Unusual Edibles']

# Create the lists for LOCATIONS that match the name of the ListField in the models.py
city = ['New York', 'San Francisco']
price = ['$','$$','$$$','$$$$','$$$$$']
hourOpen = ['12:00am', '1:00am', '2:00am', '3:00am', '4:00am', '5:00am', '6:00am', '7:00am', '8:00am', '9:00am', '10:00am', '11:00am', '12:00pm', '1:00pm', '2:00pm', '3:00pm', '4:00pm', '5:00pm', '6:00pm', '7:00pm', '8:00pm', '9:00pm', '10:00pm', '11:00pm']
hourClose = ['12:00am', '1:00am', '2:00am', '3:00am', '4:00am', '5:00am', '6:00am', '7:00am', '8:00am', '9:00am', '10:00am', '11:00am', '12:00pm', '1:00pm', '2:00pm', '3:00pm', '4:00pm', '5:00pm', '6:00pm', '7:00pm', '8:00pm', '9:00pm', '10:00pm', '11:00pm']



# --------- Routes ----------

# this is our main page
@app.route("/")
def indexAlice():
	# render the template, retrieve 'experiences' from the database
	return render_template("main_alice.html", experiences=models.Experience.objects())

# this is our main page
@app.route("/submit", methods=['GET','POST'])
def submit():

	# get Experience form from models.py
	photo_upload_form = models.photo_upload_form(request.form)

	# get created lists
	app.logger.debug(request.form.getlist('interest'))
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

		if request.form.getlist('period'):
			for p in request.form.getlist('period'):
				photo_upload_form.interest.append_entry(p)
		
		# render the template
		templateData = {
			'experiences' : experiences,
			'interest' : interest,
			'period': period,
			'form' : photo_upload_form
		}

		return render_template("submit.html", **templateData)


# pages for experiences
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
	return render_template('experience_entry.html', **templateData)



# submit locations for experiences
@app.route("/experiences/<experience_id>/location", methods=['POST'])
def submit_location(experience_id):

	# get created lists
	app.logger.debug(request.form.getlist('city'))

	# show location details (retrieving the data from the database)
	name = request.form.get('name')
	address = request.form.get('address')
	neighborhood = request.form.get('neighborhood')
	website = request.form.get('name')
	phone = request.form.get('phone')

	if name == '' or address == '' or neighborhood == '' or website == '' or phone == '':
		# no name or comment, return to page
		return redirect(request.referrer)

	# get experience by experience_slug
	try:
		experience = models.Experience.objects.get(id=experience_id)
	except:
		# error, return to where you came from
		return redirect(request.referrer)

	# create a location
	location = models.Location()
	location.name = request.form.get('name')
	location.address = request.form.get('address')
	location.neighborhood = request.form.get('neighborhood')
	location.website = request.form.get('website')
	location.phone = request.form.get('phone')
	
	# append locations to experience
	experience.locations.append(location)

	# save it
	experience.save()

	return redirect('/experiences/%s' % experience.slug)





@app.route('/delete/<imageid>')
def delete_image(imageid):
	
	image = models.Experience.objects.get(id=imageid)
	if image:

		# delete from s3
	
		# connect to s3
		s3conn = boto.connect_s3(os.environ.get('AWS_ACCESS_KEY_ID'),os.environ.get('AWS_SECRET_ACCESS_KEY'))

		# open s3 bucket, create new Key/file
		# set the mimetype, content and access control
		bucket = s3conn.get_bucket(os.environ.get('AWS_BUCKET')) # bucket name defined in .env
		k = bucket.new_key(bucket)
		k.key = image.filename
		bucket.delete_key(k)

		# delete from Mongo	
		image.delete()

		return redirect('/')

	else:
		return "Unable to find requested image in database."




# --------- Additional Basic Pages ------------------------------------------------------------------

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

# --------- Server On ----------
# start the webserver
if __name__ == "__main__":
	app.debug = True
	
	port = int(os.environ.get('PORT', 5000)) # locally PORT 5000, Heroku will assign its own port
	app.run(host='0.0.0.0', port=port)




	