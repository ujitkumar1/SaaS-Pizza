import os
from datetime import datetime
from json import JSONEncoder

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from flask_jwt_simple import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse
from flask_sqlalchemy import SQLAlchemy


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, datetime):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


app = Flask(__name__)
jwt = JWTManager(app)

# Use the 'instance_relative_config' parameter to make the path relative to the instance folder
db_folder = os.path.join(app.instance_path, 'db')
os.makedirs(db_folder, exist_ok=True)

# Specify the database file path
db_path = os.path.join(db_folder, 'pizza.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'your-secret-key'  # Change this to a secure secret key

# Set the custom JSON encoder for the app
app.json_encoder = CustomJSONEncoder

api = Api(app)
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    body = db.Column(db.Text, nullable=False)
    expiration_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='Live')
    owner_name = db.Column(db.String(80), nullable=False)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)


class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(80), nullable=False)
    interaction_value = db.Column(db.String(20), nullable=False)
    time_left = db.Column(db.String(20), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)


class UserRegistration(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('username', help='This field cannot be blank', required=True)
        parser.add_argument('password', help='This field cannot be blank', required=True)

        data = parser.parse_args()

        if User.query.filter_by(username=data['username']).first():
            return {'message': 'User {} already exists'.format(data['username'])}

        new_user = User(
            username=data['username'],
            password=data['password']
        )

        db.session.add(new_user)
        db.session.commit()

        return {'message': 'User {} created successfully'.format(data['username'])}


class UserLogin(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('username', help='This field cannot be blank', required=True)
        parser.add_argument('password', help='This field cannot be blank', required=True)

        data = parser.parse_args()
        current_user = User.query.filter_by(username=data['username']).first()

        if current_user and current_user.password == data['password']:
            access_token = create_access_token(identity=data['username'])
            return {'access_token': access_token}
        else:
            return {'message': 'Invalid credentials'}


class PostMessage(Resource):
    @jwt_required  # Use the correct decorator from flask_jwt_simple
    def post(self):
        # Create a new parser for the post-related fields
        post_parser = reqparse.RequestParser()
        post_parser.add_argument('title', help='This field cannot be blank', required=True)
        post_parser.add_argument('topic', help='This field cannot be blank', required=True)
        post_parser.add_argument('body', help='This field cannot be blank', required=True)
        post_parser.add_argument('expiration_time', help='This field cannot be blank', required=True)

        # Get the current user from the JWT token
        current_user = get_jwt_identity()

        # Parse the request data using the post_parser
        data = post_parser.parse_args()

        # Extract post details from data
        title = data['title']
        topic = data['topic']
        body = data['body']
        expiration_time = datetime.strptime(data['expiration_time'], '%Y-%m-%dT%H:%M:%S')

        # Save post details to the database with the current_user as the owner
        new_post = Post(
            title=title,
            topic=topic,
            body=body,
            expiration_time=expiration_time,
            owner_name=current_user
        )

        db.session.add(new_post)
        db.session.commit()

        return {'message': 'Post created successfully'}


class BrowseMessages(Resource):
    @jwt_required
    def get(self, topic_name):
        # Get the current user from the JWT token
        current_user = get_jwt_identity()

        # Retrieve messages related to the specified topic
        messages = Post.query.filter_by(topic=topic_name, status='Live').all()

        # Create a list to store the messages
        result = []

        # Iterate through the messages and create a response
        for message in messages:
            result.append({
                'title': message.title,
                'topic': message.topic,
                'timestamp': message.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                'body': message.body,
                'expiration_time': message.expiration_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'owner_name': message.owner_name,
                'likes': message.likes,
                'dislikes': message.dislikes
            })

        return {'messages': result}


# ... (your existing code)

class UserInteractions(Resource):
    @jwt_required
    def post(self, post_id):
        current_user = get_jwt_identity()

        # Parse the request data for user interactions
        interaction_parser = reqparse.RequestParser()
        interaction_parser.add_argument('interaction_type', help='Interaction type is required', required=True)
        interaction_parser.add_argument('time_left', help='Time left is required', required=True)

        data = interaction_parser.parse_args()

        interaction_type = data['interaction_type']
        time_left = data['time_left']

        # Check if the interaction type is valid
        if interaction_type not in ['like', 'dislike', 'comment']:
            return {'message': 'Invalid interaction type'}, 400

        # Check if the post exists
        post = Post.query.get(post_id)
        if not post:
            return {'message': 'Post not found'}, 404

        # Perform the requested interaction
        if interaction_type == 'like':
            post.likes += 1
        elif interaction_type == 'dislike':
            post.dislikes += 1
        elif interaction_type == 'comment':
            # You can implement your logic for handling comments here
            # For example, you might want to save the comment to a separate Comment model
            pass

        # Save the changes to the database
        db.session.commit()

        return {'message': f'{interaction_type.capitalize()} added successfully'}


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    api.add_resource(UserRegistration, '/register')
    api.add_resource(UserLogin, '/login')
    api.add_resource(PostMessage, '/post')
    api.add_resource(BrowseMessages, '/topic/<string:topic_name>')
    api.add_resource(UserInteractions, '/interaction/<int:post_id>')
    app.run(debug=True)
