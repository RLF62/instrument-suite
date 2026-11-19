"""No-hardware preview of the suite's future-instrument page pattern."""
from flask import Flask, render_template, redirect
import suite_navigation

app = Flask(__name__)
# Preview-only registration. A real tool belongs in the reviewed suite registry.
suite_navigation.TITLES['starter'] = 'NEW INSTRUMENT PREVIEW'
suite_navigation.VIEWS['starter'] = ('/classic', '/modern')
suite_navigation.DOCS['starter'] = '/docs/'
suite_navigation.install(app, current='starter')

@app.get('/')
def home():
    return redirect('/classic')

@app.get('/classic')
def classic():
    return render_template('instrument.html', view='Classic')

@app.get('/modern')
def modern():
    return render_template('instrument.html', view='Modern')

@app.get('/docs/')
def docs():
    return '<!doctype html><html lang="en"><title>Starter documentation</title><body><h1>New instrument documentation</h1><p>Replace this preview with the instrument manual and setup instructions.</p></body></html>'

if __name__ == '__main__':
    # Preview is only reachable from the development Pi until explicitly deployed.
    app.run(host='127.0.0.1', port=8099)
