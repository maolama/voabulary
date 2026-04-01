from app import create_app
from app.extensions import db
from flask_migrate import upgrade # NEW

app = create_app()

if __name__ == '__main__':
    # Automatically apply any pending database migrations at startup!
    with app.app_context():
        # This acts exactly like Liquibase's startup check
        upgrade()
    app.run(debug=True, port=5000)