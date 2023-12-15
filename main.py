import os
import warnings
from datetime import datetime
from json import JSONEncoder

from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, create_access_token
from flask_jwt_simple import jwt_required, get_jwt_identity
from flask_restful import Api, Resource, reqparse
from flask_sqlalchemy import SQLAlchemy

warnings.filterwarnings('ignore')


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

db_folder = os.path.join(app.instance_path, 'db')
os.makedirs(db_folder, exist_ok=True)

db_path = os.path.join(db_folder, 'pizza.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'Pizza123'

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
    @jwt_required
    def post(self):
        post_parser = reqparse.RequestParser()
        post_parser.add_argument('title', help='This field cannot be blank', required=True)
        post_parser.add_argument('topic', help='This field cannot be blank', required=True)
        post_parser.add_argument('body', help='This field cannot be blank', required=True)
        post_parser.add_argument('expiration_time', help='This field cannot be blank', required=True)

        current_user = get_jwt_identity()

        data = post_parser.parse_args()

        title = data['title']
        topic = data['topic']
        body = data['body']
        expiration_time = datetime.strptime(data['expiration_time'], '%Y-%m-%dT%H:%M:%S')

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
    def get(self, topic_name, post_id=None):
        current_user = get_jwt_identity()

        if post_id is not None:
            post = Post.query.filter_by(id=post_id, topic=topic_name, status='Live').first()
            if not post:
                return {'message': 'Post not found'}, 404

            return {
                'id': post.id,
                'title': post.title,
                'topic': post.topic,
                'timestamp': post.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                'expiration_time': post.expiration_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'owner_name': post.owner_name,
                'body': post.body,
                'likes': post.likes,
                'dislikes': post.dislikes
            }

        messages = Post.query.filter_by(topic=topic_name, status='Live').all()

        result = []

        for message in messages:
            result.append({
                'id': message.id,
                'title': message.title,
                'topic': message.topic,
                'timestamp': message.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                'expiration_time': message.expiration_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'owner_name': message.owner_name,
                'likes': message.likes,
                'dislikes': message.dislikes
            })

        return {'messages': result}


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)


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

        if interaction_type not in ['like', 'dislike', 'comment']:
            return {'message': 'Invalid interaction type'}, 400

        post = Post.query.get(post_id)
        if not post:
            return {'message': 'Post not found'}, 404

        if interaction_type == 'like':
            post.likes += 1
        elif interaction_type == 'dislike':
            post.dislikes += 1
        elif interaction_type == 'comment':
            comment_parser = reqparse.RequestParser()
            comment_parser.add_argument('comment_text', help='Comment text is required', required=True)

            comment_data = comment_parser.parse_args()
            comment_text = comment_data['comment_text']

            new_comment = Comment(
                user_name=current_user,
                text=comment_text,
                post_id=post_id
            )
            db.session.add(new_comment)

        db.session.commit()

        return {'message': f'{interaction_type.capitalize()} added successfully'}


class ViewComments(Resource):
    @jwt_required
    def get(self, post_id):
        post = Post.query.filter_by(id=post_id, status='Live').first()
        if not post:
            return {'message': 'Post not found'}, 404

        comments = Comment.query.filter_by(post_id=post_id).all()

        result = []

        for comment in comments:
            result.append({
                'id': comment.id,
                'user_name': comment.user_name,
                'text': comment.text,
                'post_id': comment.post_id
            })

        return {'comments': result}


class PostComment(Resource):
    @jwt_required
    def post(self, post_id):
        current_user = get_jwt_identity()

        comment_parser = reqparse.RequestParser()
        comment_parser.add_argument('comment_text', help='Comment text is required', required=True)

        comment_data = comment_parser.parse_args()
        comment_text = comment_data['comment_text']

        post = Post.query.get(post_id)
        if not post:
            return {'message': 'Post not found'}, 404

        new_comment = Comment(
            user_name=current_user,
            text=comment_text,
            post_id=post_id
        )
        db.session.add(new_comment)
        db.session.commit()

        return {'message': 'Comment added successfully'}


class MostActivePosts(Resource):
    @jwt_required
    def get(self):
        topics = db.session.query(Post.topic).distinct().all()

        most_active_posts = {}

        for topic in topics:
            topic_name = topic[0]

            most_active_post = Post.query.filter_by(topic=topic_name, status='Live') \
                .order_by(Post.likes.desc(), Post.dislikes.desc()).first()

            if most_active_post:
                most_active_posts[topic_name] = {
                    'id': most_active_post.id,
                    'title': most_active_post.title,
                    'topic': most_active_post.topic,
                    'timestamp': most_active_post.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                    'expiration_time': most_active_post.expiration_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'owner_name': most_active_post.owner_name,
                    'likes': most_active_post.likes,
                    'dislikes': most_active_post.dislikes
                }

        return jsonify(most_active_posts)


class ExpiredPosts(Resource):
    @jwt_required
    def get(self, topic_name):
        current_user = get_jwt_identity()

        expired_posts = Post.query.filter_by(topic=topic_name, status='Expired').all()

        history_data = []

        for expired_post in expired_posts:
            history_data.append({
                'id': expired_post.id,
                'title': expired_post.title,
                'topic': expired_post.topic,
                'timestamp': expired_post.timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                'expiration_time': expired_post.expiration_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'owner_name': expired_post.owner_name,
                'likes': expired_post.likes,
                'dislikes': expired_post.dislikes
            })

        return jsonify({'history_data': history_data})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    api.add_resource(UserRegistration, '/register')
    api.add_resource(UserLogin, '/login')
    api.add_resource(PostMessage, '/post')
    api.add_resource(BrowseMessages, '/topic/<string:topic_name>', '/topic/<string:topic_name>/<int:post_id>')
    api.add_resource(UserInteractions, '/interaction/<int:post_id>')
    api.add_resource(ViewComments, '/comments/<int:post_id>')
    api.add_resource(PostComment, '/comment/<int:post_id>')
    api.add_resource(MostActivePosts, '/most_active_posts')
    api.add_resource(ExpiredPosts, '/expired_posts/<string:topic_name>')
    
    app.run(debug=True)
