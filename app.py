from functools import wraps
from flask import Flask, render_template, flash, redirect, url_for, session, request, send_file
from flask_table import Table, Col
from flask_mysqldb import MySQL
from passlib.hash import sha256_crypt
from wtforms import Form, StringField, SelectField, IntegerField, PasswordField, BooleanField, FloatField, validators
from wtforms.fields.html5 import EmailField
import json
from xlwt import Workbook
import os

from crispr.Crispr import Crispr
from fastadict.SimpleFastaDictionary import SimpleFastaDictionary
from target_sink.JsonFileTargetSink import JsonFileTargetSink
from target_sink.JsonStringTargetSink import JsonStringTargetSink
from target_sink.BedFileTargetSink import BedFileTargetSink
from target_index.FastaFileTargetIndex import FastaFileTargetIndex
from scorer.GcContentScorer import GcContentScorer
# from scorer.MitSpecificityScorer import MitSpecificityScorer
from scorer.NewMitScorer import NewMitScorer
from scorer.DoenchScorer import DoenchScorer
from roi_source.JsonFileRoiSource import JsonFileRoiSource
from roi_source.JsonStringRoiSource import JsonStringRoiSource

app = Flask(__name__)

# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'password'
app.config['MYSQL_DB'] = 'crisprapp'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# init MYSQL
mysql = MySQL(app)

app.config['UPLOAD_FOLDER'] = '/home/nadine/project/crisprapp/uploads'


@app.template_filter()
def numberFormat(value):
    return format(int(value), ',d')


@app.route('/')
def index():
    return render_template('home.html')


# @app.route('/jbrowse')
# def jbrowse():
#    return render_template('jbrowse.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route("/done")
def done():
    return "Done!"


@app.route("/slow")
def slow():
    import time
    time.sleep(5)
    return "oh so slow"


@app.route('/crispr', methods=['GET', 'POST'])
def crispr(framesize, data_json, minimum_score):
    framesize = framesize
    data_json = data_json
    score_minimum = minimum_score
    Crispr(JsonStringRoiSource(data_json, framesize), FastaFileTargetIndex('GRCh38.fna', SimpleFastaDictionary()),
           NewMitScorer(), GcContentScorer(), DoenchScorer(), JsonFileTargetSink('GiveMeTargets'),
           score_minimum).perform()
    # Crispr(JsonStringRoiSource(data_json, framesize), FastaFileTargetIndex('GRCh38.fna', SimpleFastaDictionary()), NewMitScorer(), GcContentScorer(), DoenchScorer(), BedFileTargetSink('BedTargets.bed', 'Crispr gDNAs', 'targets', '2', "255,0,0 0,0,255"), score_minimum).perform()
    return targets()


# targets
@app.route('/targets', methods=['POST', 'GET'])
def targets():
    with open('GiveMeTargets.json') as f:
        # Get targets
        targets = json.load(f)
    return render_template('targets.html', data_json=targets)


@app.route('/download_exel/')
def download_exel(selected_targets, target_list):
    # Workbook is created
    wb = Workbook()
    # add_sheet is used to create sheet.
    sheet1 = wb.add_sheet('Sheet 1')
    # Write the headers
    sheet1.write(0, 0, 'target_id')
    sheet1.write(0, 1, 'chromosome')
    sheet1.write(0, 2, 'start')
    sheet1.write(0, 3, 'stop')
    sheet1.write(0, 4, 'mit_score')
    sheet1.write(0, 5, 'gc_score')
    sheet1.write(0, 6, 'doench_score')
    sheet1.write(0, 7, 'strand')
    sheet1.write(0, 8, 'sequence')

    i = 0
    for item in selected_targets:
        i = i + 1
        index = int(item) - 1
        target_dict = target_list[index]

        sheet1.write(i, 0, target_dict['target_id'])
        sheet1.write(i, 1, target_dict['chromosome'])
        sheet1.write(i, 2, target_dict['start'])
        sheet1.write(i, 3, target_dict['stop'])
        sheet1.write(i, 4, target_dict['mit_score'])
        sheet1.write(i, 5, target_dict['gc_score'])
        sheet1.write(i, 6, target_dict['doench_score'])
        sheet1.write(i, 7, target_dict['strand'])
        sheet1.write(i, 8, target_dict['sequence'])

    wb.save('targets.xls')


def get_user_id():
    # Create cursor
    cur = mysql.connection.cursor()
    # Get User ID
    cur.execute("SELECT user_id FROM users WHERE username=%s", [session['username']])
    user = cur.fetchone()
    user_id = str(user['user_id'])
    return user_id


@app.route('/handle_target_selection', methods=['POST'])
def handle_target_selection():
    with open('GiveMeTargets.json') as f:
        # Get targets
        f = json.load(f)
        target_list = f['targets']
        user_id = get_user_id()

    if request.method == "POST":
        # Get selected targets from checkbox
        selected_targets = request.form.getlist('target_index')
        print('Selected targets', selected_targets)
        # Create cursor
        cur = mysql.connection.cursor()

        for item in selected_targets:
            list_index = int(item) - 1
            target_dict = target_list[list_index]
            roi_id = str(target_dict['name'])

            print('roi id', roi_id, 'user_id', user_id)
            cur.execute("SELECT experiment_id FROM rois WHERE roi_id=%s AND user_id=%s", (roi_id, user_id))
            experiment = cur.fetchone()
            experiment_id = experiment['experiment_id']
            print('exp id target selection', experiment_id)

            # Create new DB entry for the chosen targets
            sql = "INSERT INTO selected_targets(target_id, chromosome, start, stop, gc_score, m_score, d_score, strand, sequence, roi_id, experiment_id) VALUES(%s, %s, %s,%s,%s,%s,%s,%s,%s,%s,%s);"
            val = (target_dict['target_id'], target_dict['chromosome'], target_dict['start'], target_dict['stop'],
                   target_dict['gc_score'], target_dict['mit_score'], target_dict['doench_score'],
                   target_dict['strand'], target_dict['sequence'], target_dict['name'], experiment_id)
            cur.execute(sql, val)
            mysql.connection.commit()

        cur.close()
        download_exel(selected_targets, target_list)
        # Select data from json file for each selected target

        return send_file(filename_or_fp='/home/nadine/project/crisprapp/targets.xls', attachment_filename='targets.xls',
                         as_attachment=True)
    return render_template('home.html')


class ExperimentDetailsForm(Form):
    framesize = IntegerField('Select a frame size between 0 and 5000', [validators.NumberRange(min=0, max=5000)],
                             default=0)
    minimum_score = IntegerField('Select a minimum MIT target score between 0 and 100',
                                 [validators.NumberRange(min=0, max=100)], default=40)
    experiment_name = StringField('Experiment name', [validators.Length(min=3, max=30)])


# Rois
@app.route('/rois', methods=['GET', 'POST'])
def rois():

    # Create cursor
    cur = mysql.connection.cursor()

    # Get User ID
    user_id = get_user_id()

    form = ExperimentDetailsForm(request.form)

    if request.method == "POST" and form.validate():

        # Get frame size
        framesize = form.framesize.data
        # Get minimum score
        minimum_score = form.minimum_score.data
        # Get experiment name
        experiment_name = form.experiment_name.data
        # Get selected ROIs from checkbox
        selected_rois = request.form.getlist('roi_index')

        # Create new experiment DB entry for the chosen ROIS
        cur.execute("INSERT INTO experiments(user_id, experiment_name) VALUES(%s, %s)", (user_id, experiment_name))
        # Get created experiment ID
        cur.execute("SELECT * FROM experiments WHERE experiment_name=%s AND user_id=%s",
                    (str(experiment_name), user_id))
        experiment = cur.fetchone()
        experiment_id = experiment['experiment_id']

        # Write json file
        data_json = {}
        data_json['rois'] = []

        # Update selected ROIs with the experiment ID
        for item in selected_rois:
            sql = "UPDATE rois SET experiment_id = %s WHERE roi_id = %s;"
            val = (experiment_id, str(item))
            cur.execute(sql, val)
            # Commit to DB
            mysql.connection.commit()

            # Get roi data
            cur.execute("SELECT * FROM rois WHERE roi_id = %s;", [item])
            roi = cur.fetchone()

            # Write roi data as json data
            # Sets roi_id as roi_name for json dump to reference targets correctly. Names can be duplicated
            data_json['rois'].append({
                'chromosome': roi['chromosome'],
                'start': roi['start'],
                'stop': roi['stop'],
                'name': roi['roi_id'],
                'score': '0',
                'strand': roi['strand'],
                'full_region': str(roi['full_region'])
            })

        data_json = json.dumps(data_json, indent=4)
        print("mini score:", minimum_score)

        return crispr(framesize, data_json, minimum_score)

        # return redirect(url_for('crispr', data_json=data_json, framesize=framesize, minimum_score=minimum_score))
        # return render_template('redirect.html', data_json=data_json, framesize=framesize, minimum_score=minimum_score)
        # return render_template('crispr.html', data_json=data_json, framesize=framesize, minimum_score=minimum_score)

    # Get rois
    cur.execute("SELECT * FROM rois WHERE user_id = %s", [user_id])
    rois = cur.fetchall()
    return render_template('rois.html', rois=rois, form=form)

    # Close connection
    cur.close()


# History
@app.route('/history', methods=['GET', 'POST'])
def history():
    # Create cursor
    cur = mysql.connection.cursor()
    # Get User ID
    user_id = get_user_id()

    # Get experiments
    result = cur.execute("SELECT * FROM experiments WHERE user_id = %s", [user_id])
    experiments = cur.fetchall()

    if result > 0:
        return render_template('history.html', experiments=experiments)
    else:
        msg = 'No experiments found'
        return render_template('history.html', msg=msg)
        # Close connection
    cur.close()

    return render_template('history.html')


# Targets Form Class
class TargetsForm(Form):
    enrichment = SelectField('Provides Enrichment?', choices=['Yes', 'No'], validate_choice=False)
    read_amount = IntegerField('Reads', [validators.InputRequired()])
    coverage = FloatField('Coverage', [validators.InputRequired()])
    off_targets = IntegerField('Off targets', [validators.InputRequired()])
    platform = SelectField('Platform', choices=['Flongle', 'MinION', 'PromethION'], validate_choice=False)


# Selected history information
@app.route('/experiment_details/<string:id>/')
def experiment_details(id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM selected_targets WHERE experiment_id=%s", [id])
    experiments = cur.fetchall()
    cur.close()

    return render_template('experiment_details.html', experiments=experiments)


@app.route('/update_targets/<string:id>', methods=['GET', 'POST'])
def update_targets(id):
    cur = mysql.connection.cursor()
    # Get target by id
    cur.execute("SELECT * FROM selected_targets WHERE exp_target_id = %s", [id])
    target = cur.fetchone()
    exp_id = target['experiment_id']

    # Get form
    form = TargetsForm(request.form)

    # Populate Form with DB entry
    form.off_targets.data = target['off_targets']
    form.coverage.data = target['coverage']
    form.enrichment.data = target['enrichment']
    form.read_amount.data = target['read_amount']
    form.platform.data = target['platform']

    # Get User input
    if request.method == 'POST' and form.validate():
        enrichment = request.form['enrichment']
        read_amount = request.form['read_amount']
        coverage = request.form['coverage']
        off_targets = request.form['off_targets']
        platform = request.form['platform']

        # Calculate average coverage depending on platform
        if platform == 'Flongle':
            coverage = float(coverage) / 0.5
        elif platform == 'MinION':
            coverage = float(coverage) / 10.0
        else:
            coverage = float(coverage) / 40.0

        cur.execute(
            "UPDATE selected_targets SET enrichment=%s, off_targets=%s, coverage=%s, read_amount=%s, platform=%s WHERE exp_target_id=%s",
            (enrichment, off_targets, coverage, read_amount, platform, id))

        # Commit to DB
        mysql.connection.commit()
        flash('Target Updated', 'success')

        # Close connection
        cur.close()

        return redirect(url_for('experiment_details', id=exp_id))

    return render_template('update_targets.html', form=form)


# Register Form Class
class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = EmailField('Email address', [validators.DataRequired(), validators.Email()])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')
    institute = StringField('Institute', [validators.Length(min=1, max=30)])
    country = StringField('Country', [validators.Length(min=1, max=30)])


# User Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))
        institute = form.institute.data
        country = form.country.data

        print("username:", username)

        # Create cursor
        cur = mysql.connection.cursor()

        x = cur.execute("SELECT * FROM users WHERE username = %s", [username])
        print("x", int(x))

        if int(x) > 0:
            flash("That username is already taken, please choose another", 'danger')
            return render_template('register.html', form=form)

        else:
            # Execute query
            cur.execute(
                "INSERT INTO users(name, email, username, password, country, institute) VALUES(%s, %s, %s, %s, %s, %s)",
                (name, email, username, password, country, institute))

            # Commit to DB
            mysql.connection.commit()

            # Close connection
            cur.close()

            flash('You are now registered and can log in', 'success')

            return redirect(url_for('login'))

    return render_template('register.html', form=form)


# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get Form Fields
        username = request.form['username']
        password_candidate = request.form['password']

        # Create cursor
        cur = mysql.connection.cursor()

        # Get user by username
        result = cur.execute("SELECT * FROM users WHERE username = %s", [username])

        if result > 0:
            # Get stored hash
            data = cur.fetchone()
            password = data['password']

            # Compare Passwords
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = username

                flash('You are now logged in', 'success')
                return redirect(url_for('index'))
            else:
                error = 'Invalid login'
                return render_template('login.html', error=error)
            # Close connection
            cur.close()
        else:
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')


# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))

    return wrap


# Logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))


# Dashboard
@app.route('/dashboard')
@is_logged_in
def dashboard():
    # Create cursor
    cur = mysql.connection.cursor()

    # Get User ID
    cur.execute("SELECT user_id FROM users WHERE username=%s", [session['username']])
    user = cur.fetchone()
    user_id = str(user['user_id'])
    print('user id', user_id)

    # Show rois only from the user logged in
    result = cur.execute("SELECT * FROM rois WHERE user_id = %s", [user_id])
    print("result:", result)

    # Get rois
    rois = cur.fetchall()

    if result > 0:
        return render_template('dashboard.html', rois=rois)
    else:
        msg = 'No Rois Found'
        return render_template('dashboard.html', msg=msg)
    # Close connection
    cur.close()


@app.route('/user')
@is_logged_in
def user():
    # Create cursor
    cur = mysql.connection.cursor()
    result = cur.execute("SELECT * FROM users WHERE username=%s", [session['username']])
    user = cur.fetchall()

    if result > 0:
        return render_template('users.html', user=user)
    else:
        msg = 'No User Found'
        return render_template('users.html', msg=msg)
    # Close connection
    cur.close()


# Edit Roi
@app.route('/edit_user/', methods=['GET', 'POST'])
@is_logged_in
def edit_user():
    # Create cursor
    cur = mysql.connection.cursor()
    # Get User ID
    cur.execute("SELECT * FROM users WHERE username=%s", [session['username']])
    user = cur.fetchone()
    user_id = str(user['user_id'])

    # Get form
    form = RegisterForm(request.form)
    if request.method == 'GET':
        # Populate Form with DB entry
        form.name.data = user['name']
        form.email.data = user['email']
        form.username.data = user['username']
        form.country.data = user['country']
        form.institute.data = user['institute']

    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))
        institute = form.institute.data
        country = form.country.data

        # Execute query
        cur.execute(
            "UPDATE users SET name=%s, email=%s, username=%s, password=%s, country=%s, institute=%s WHERE user_id=%s",
            (name, email, username, password, country, institute, [user_id]))

        # Commit to DB
        mysql.connection.commit()

        # Close connection
        cur.close()

        # Update new username
        session['username'] = username

        flash('You updated your personal information', 'success')

        return redirect(url_for('user'))

    return render_template('edit_user.html', form=form)


# Upload BED File
@app.route('/upload', methods=['GET', 'POST'])
@is_logged_in
def upload_file():
    if request.method == 'POST':
        if request.files:
            f = request.files['file']
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], f.filename))
            handle_upload_file(f)
            flash('file uploaded successfully', 'success')
    return render_template('upload.html')


class Entry:

    def __init__(self, chromosome: str, start: int, stop: int, name: str, score: float, strand: str, full_region: bool):
        self.chromosome = chromosome
        self.start = start
        self.stop = stop
        self.name = name
        self.score = score
        self.strand = strand
        self.full_region = full_region


def from_bed_string(string: str):
    parts = string.strip().split()
    chromosome = parts[0]
    start = int(parts[1])
    stop = int(parts[2])
    name = parts[3]
    score = float(parts[4])
    strand = parts[5]
    full_region = "1" == parts[6]

    # Save ROIs in DB:
    # Create Cursor
    cur = mysql.connection.cursor()

    # Get User ID
    user_id = get_user_id()
    experiment_id = '1'

    # Execute
    cur.execute(
        "INSERT INTO rois(chromosome, start, stop, name, strand, full_region, experiment_id, user_id) VALUES(%s, "
        "%s, %s, %s, "
        "%s, %s, %s, %s)",
        (chromosome, start, stop, name, strand, full_region, experiment_id, user_id))

    # Commit to DB
    mysql.connection.commit()

    # Close connection
    cur.close()

    return Entry(chromosome, start, stop, name, score, strand, full_region)


@app.route('/handle_upload_file')
def handle_upload_file(file):
    file_name = file.filename
    data_folder = '/home/nadine/project/crisprapp/uploads/'
    file_to_open = data_folder + file_name
    file = open(file_to_open, "rb")
    for line in file:
        print("input: " + line.decode('utf-8').strip())
        entry = from_bed_string(line.decode("utf-8", "replace"))
        print(entry)


# Roi Form Class
class RoiForm(Form):
    chromosome = SelectField('Chromosome',
                             choices=['chr1', 'chr2', 'chr3', 'chr4', 'chr5', 'chr6', 'chr7', 'chr8', 'chr9', 'chr10',
                                      'chr11', 'chr12',
                                      'chr13', 'chr14', 'chr15', 'chr16', 'chr17', 'chr18', 'chr19', 'chr20', 'chrX',
                                      'chrY'], validate_choice=False)
    start = IntegerField('Start', [validators.NumberRange(min=0)])
    stop = IntegerField('Stop', [validators.NumberRange(min=1)])
    name = StringField('Name', [validators.Length(min=1, max=100)])
    strand = SelectField('Strand', choices=['+', '-'], validate_choice=False)
    full_region = SelectField('Full_Region', choices=['1', '0'], validate_choice=False)


# Add Roi
@app.route('/add_roi', methods=['GET', 'POST'])
@is_logged_in
def add_roi():
    form = RoiForm(request.form)
    if request.method == 'POST' and form.validate():
        chromosome = form.chromosome.data
        start = form.start.data
        stop = form.stop.data
        name = form.name.data
        strand = form.strand.data
        full_region = form.full_region.data

        # Create Cursor
        cur = mysql.connection.cursor()

        # Get User ID
        user_id = get_user_id()
        experiment_id = '1'

        # Execute
        cur.execute(
            "INSERT INTO rois(chromosome, start, stop, name, strand, full_region, experiment_id, user_id) VALUES(%s, "
            "%s, %s, %s, "
            "%s, %s, %s, %s)",
            (chromosome, start, stop, name, strand, full_region, experiment_id, user_id))

        # Commit to DB
        mysql.connection.commit()

        # Close connection
        cur.close()

        flash('Roi Created', 'success')

        return redirect(url_for('dashboard'))

    return render_template('add_roi.html', form=form)


# Edit Roi
@app.route('/edit_rois/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def edit_rois(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Get roi by id
    result = cur.execute("SELECT * FROM rois WHERE roi_id = %s", [id])

    roi = cur.fetchone()
    cur.close()
    # Get form
    form = RoiForm(request.form)

    # Populate roi form fields
    form.chromosome.data = roi['chromosome']
    form.start.data = roi['start']
    form.stop.data = roi['stop']
    form.name.data = roi['name']
    form.strand.data = roi['strand']
    form.full_region.data = roi['full_region']

    if request.method == 'POST' and form.validate():
        chromosome = request.form['chromosome']
        start = request.form['start']
        stop = request.form['stop']
        name = request.form['name']
        strand = request.form['strand']
        full_region = request.form['full_region']

        # Create Cursor
        cur = mysql.connection.cursor()
        app.logger.info(chromosome)
        # Execute
        cur.execute(
            "UPDATE rois SET chromosome=%s, start=%s, stop=%s, name=%s, strand=%s, full_region=%s WHERE roi_id=%s",
            (chromosome, start, stop, name, strand, full_region, id))
        # Commit to DB
        mysql.connection.commit()

        # Close connection
        cur.close()

        flash('Roi Updated', 'success')

        return redirect(url_for('dashboard'))

    return render_template('edit_rois.html', form=form)


# Delete Roi
@app.route('/delete_roi/<string:id>', methods=['POST'])
@is_logged_in
def delete_roi(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Execute
    cur.execute("DELETE FROM rois WHERE roi_id = %s", [id])

    # Commit to DB
    mysql.connection.commit()

    # Close connection
    cur.close()

    flash('Roi Deleted', 'success')

    return redirect(url_for('dashboard'))


# Delete experiment
@app.route('/delete_experiment/<string:id>', methods=['POST'])
@is_logged_in
def delete_experiment(id):
    # Create cursor
    cur = mysql.connection.cursor()

    # Execute
    cur.execute("DELETE FROM selected_targets WHERE experiment_id = %s", [id])
    cur.execute("UPDATE rois SET experiment_id = 1 WHERE experiment_id = %s", [id])
    cur.execute("DELETE FROM experiments WHERE experiment_id = %s", [id])

    # Commit to DB
    mysql.connection.commit()

    # Close connection
    cur.close()

    flash('Experiment Deleted', 'success')

    return redirect(url_for('history'))


# Delete user
@app.route('/delete_user/', methods=['POST'])
@is_logged_in
def delete_user():
    # Create cursor
    cur = mysql.connection.cursor()
    # Get User ID
    user_id = get_user_id()
    # Execute
    if request.method == 'POST':
        print("Funktionsaufruf")
        cur.execute("UPDATE rois SET user_id = 1 WHERE user_id = %s", [user_id])
        cur.execute("UPDATE experiments SET user_id = 1 WHERE user_id = %s", [user_id])
        cur.execute("DELETE FROM users WHERE user_id = %s", [user_id])

        mysql.connection.commit()
        flash('Deleted Account', 'success')
        print("commit")
    # Close connection
    cur.close()

    logout()

    return redirect(url_for('register'))


if __name__ == '__main__':
    # Set the secret key to a sufficiently random value
    app.secret_key = os.urandom(24)

    # Set the session cookie to be secure
    app.session_cookie_secure = True

    # Set the session cookie for our app to a unique name
    app.session_cookie_name = 'CrisprApp'

    # Set CSRF tokens to be valid for the duration of the session. This assumes you’re using WTF-CSRF protection
    app.wtf_csrf_time_limit = None
    # app.secret_key = 'secret123'
    app.run(debug=True)
