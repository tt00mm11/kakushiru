# ファイル保存なし
# ログインとcanvasが繋がったやつ
# デプロイしようとしているところ
# DBはsqlalchemy→BQ

from fileinput import filename
import imghdr
import re
import base64
from sqlite3 import Timestamp
from flask import Flask, render_template, session, request, jsonify, redirect, make_response
# sessionでcookieに引っかかったみたい？
from itsdangerous import base64_decode
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from google.oauth2 import service_account
from google.cloud import language_v1
from google.cloud.bigquery import Client
from flask_login import LoginManager,  logout_user, login_required
from flask_bootstrap import Bootstrap
from google.cloud import storage as gcs

from werkzeug.security import generate_password_hash, check_password_hash
import os

# 時間がうまくあっていない問題
from datetime import datetime
import pytz

import base64
# from PIL import Image
from io import BytesIO
from google.cloud import vision
import io

app = Flask(__name__)
credentials_path = './kakushiru-fd65da234d38.json'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
# app.config['GOOGLE_APPLICATION_CREDENTIALS'] = 'sqlite:///blog.db'
app.config['SECRET_KEY'] = os.urandom(24)
# db = SQLAlchemy(app)

bootstrap = Bootstrap(app)

client = Client()

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_name):
  query = f"select * from `kakushiru.kakushiru.user` where user_name = '{user_name}'"
  result = client.query(query)
  df = result.to_dataframe()
  dict = df.to_dict()
  return dict

@app.route('/', methods=['GET', 'POST'])
def index():
  if (session):
    if request.method== 'GET':

      query = f"select * from `kakushiru.kakushiru.data`"
      result = client.query(query)
      df = result.to_dataframe()
      dict = df.to_dict()
      data = dict

      listOfDataImg = data['img_url'].values()
      listOfDataImg = list(listOfDataImg)

      listOfText = data['text'].values()
      listOfText = list(listOfText)

      listOfEmotion = data['emotion'].values()
      listOfEmotion = list(listOfEmotion)
      
      listOfCreatedAt = data['created_at'].values()
      listOfCreatedAt = list(listOfCreatedAt)
      
      listOfUpdatedAt = data['updated_at'].values()
      listOfUpdatedAt = list(listOfUpdatedAt)

      posts = []

      # 数の分だけ出したいけど何回回せばいいん？？for文？
      for index in range(17):
        posts.append({'data_img': listOfDataImg[index], 'text': listOfText[index], 'emotion': listOfEmotion[index],'updated_at': listOfUpdatedAt[index], 'created_at': listOfCreatedAt[index]})

      return render_template('index.html', posts=posts)
    

  else:
    return render_template('login.html', message='ログインしてないよ！')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
  if request.method == 'POST':
    password = request.form.get('password')
    user_name = str(request.form.get('user_name'))

    query = f"select * from `kakushiru.kakushiru.user`"

    result = client.query(query)
    df = result.to_dataframe()
    dict = df.to_dict()
    listOfValues = dict['user_name'].values()
    listOfValues = list(listOfValues)

    dict['password'][5]

    for value in listOfValues:
      if value == user_name:
        return render_template('signup.html', message = 'このユーザー名は既に使われています')


    rows_to_insert = [{'user_name': user_name, 'password': password, 'created_at': datetime.now(pytz.timezone('Asia/Tokyo'))}]

    table = client.get_table('kakushiru.kakushiru.user')
    errors = client.insert_rows(table, rows_to_insert)
    if errors == []:
      print('Success!')

    return redirect('/login')
  else:
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
  if request.method == 'POST':
    password = request.form.get('password')
    user_name = str(request.form.get('user_name'))

    query = f"select * from `kakushiru.kakushiru.user` where user_name = '{user_name}'"

    result = client.query(query)
    df = result.to_dataframe()
    dict = df.to_dict()

    if int(password) == dict['password'][0]:
      session['user'] = dict
      print(session)
      return redirect('/')
    else:
      return render_template('login.html', message='すまん！')

  else:
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

@app.route('/create', methods=['GET', 'POST'])
def create():
  if request.method == "POST":
    img_str = re.search(r'base64,(.*)', request.json['img']).group(1)
    #エンコードされている
    # img = request.json['img']
    # print(img)
    nparr = np.fromstring(base64.b64decode(img_str), np.uint8)
    s = base64.b64encode(nparr)
    r = base64.decodebytes(s)    
    ans =  detect_text(r)
    # print(img_str)
    # 毎回フォルダが変わるようにしなきゃ！？
    filename = 'test3.png'
    svimg(r, filename)
    senti_res = sample_analyze_sentiment(ans)

    rows_to_insert = [{'img_url': 'https://storage.cloud.google.com/kakushiru.appspot.com//image/kakushiru' + filename, 'text': ans, 'emotion': senti_res, 'created_at': datetime.now(pytz.timezone('Asia/Tokyo')), 'updated_at': datetime.now(pytz.timezone('Asia/Tokyo'))}]

    table = client.get_table('kakushiru.kakushiru.data')
    errors = client.insert_rows(table, rows_to_insert)

    if errors == []:
      print('Success!')
    else:
      print(errors)

    #保存する部分
    ts = datetime.now(pytz.timezone('Asia/Tokyo')).strftime(format='%Y%m%d%H%M%S')
    svimg(r, ts)
    
    print(senti_res)  
    print(ans)
    return make_response({'ans': f'手書き文字認識の結果は : {ans}       ' + f'\t感情分析の結果は : {senti_res}'})
  else :
    return render_template('create.html')
     
def canvas(ans, senti_res):
  # if request.method == 'POST':
  print('hoge')
  data_img = request.form.get('data_img')
  text = str(request.form.get('text'))

  rows_to_insert = [{'data_img': data_img, 'text': ans, ' emotion': senti_res, 'created_at': datetime.now(pytz.timezone('Asia/Tokyo')), 'updated_at': datetime.now(pytz.timezone('Asia/Tokyo'))}]

  table = client.get_table('kakushiru.kakushiru.data')
  errors = client.insert_rows(table, rows_to_insert)
  if errors == []:
    return print('Success!')
  else:
    return render_template('/') 

    # GCSに画像保存する関数
def svimg(image, filename): 
    credentials = service_account.Credentials.from_service_account_file('kakushiru-fd65da234d38.json')
    project_id = "kakushiru"
    gcs_client = gcs.Client(project_id, credentials=credentials)
    bucket_name = "kakushiru.appspot.com"
    gcs_path = "/image/kakushiru{}".format(filename)  # 自分でファイル名決めてOK →　BQにこのアドレス保存すべし
    bucket = gcs_client.get_bucket(bucket_name)
    blob_gcs = bucket.blob(gcs_path)
    blob_gcs.upload_from_string(data=image, content_type="image/png")


def detect_text(content):
    """Detects text in the file."""
    
    
    credentials = service_account.Credentials.from_service_account_file('kakushiru-fd65da234d38.json')
    client = vision.ImageAnnotatorClient(credentials=credentials)
    image = vision.Image(content=content)

    response = client.text_detection(image=image)
    texts = response.text_annotations
    if len(texts) > 0:
        out = re.sub('\n', '', [text.description for text in texts][0])
    else:
        out ='error'
    return out

    if response.error.message:
      raise Exception(
      '{}\nFor more info on error messages, check: '
      'https://cloud.google.com/apis/design/errors'.format(response.error.message))

def sample_analyze_sentiment(text_content):
    """
    Analyzing Sentiment in a String

    Args:
      text_content The text content to analyze
    """
    credentials = service_account.Credentials.from_service_account_file('kakushiru-fd65da234d38.json')
    client = language_v1.LanguageServiceClient(credentials=credentials)

    # text_content = 'I am so happy and joyful.'

    # Available types: PLAIN_TEXT, HTML
    type_ = language_v1.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
    language = "ja"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_sentiment(request = {'document': document, 'encoding_type': encoding_type})
    # Get overall sentiment of the input document
    print()
    return response.document_sentiment.score
    
if __name__ == "__main__":
      app.run()