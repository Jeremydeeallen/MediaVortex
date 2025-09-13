from flask import Flask, render_template, jsonify
from flask_cors import CORS
from Controllers.ProfileController import ProfileController
import os


class MediaVortexApp:
    """Main Flask application for MediaVortex."""
    
    def __init__(self):
        self.App = Flask(__name__)
        self.App.config['SECRET_KEY'] = 'mediavortex-secret-key-2024'
        CORS(self.App)
        
        # Initialize controllers
        self.ProfileController = ProfileController()
        
        self._register_routes()
        self._register_blueprints()
    
    def _register_routes(self):
        """Register main application routes."""
        
        @self.App.route('/')
        def home():
            """Home page - blank for now."""
            return render_template('Home.html')
        
        @self.App.route('/settings')
        def settings():
            """Settings page with profile management."""
            return render_template('Settings.html')
        
        @self.App.route('/api/health')
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'message': 'MediaVortex is running'
            })
    
    def _register_blueprints(self):
        """Register controller blueprints."""
        self.App.register_blueprint(self.ProfileController.Blueprint, url_prefix='/api')
    
    def Run(self, host='127.0.0.1', port=5000, debug=True):
        """Run the Flask application."""
        print(f"Starting MediaVortex on http://{host}:{port}")
        print(f"Settings page: http://{host}:{port}/settings")
        self.App.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    app = MediaVortexApp()
    app.Run()
