from bottle import route, template
#import textwrap
import markdown

from Sand import *

@route('/dhelp/<method>')
def main(method):
    method = method if method in sandables else sandables[0]
    sandable = sandableFactory( method )
    if sandable:
        doc = markdown.markdown( sandable.__doc__, extensions=['tables'] ) if sandable.__doc__ else 'No documentation available'
    else:
        doc = '<div class="error">Error "%s" is not a valid drawing method!</div>' % method 

    return [ template( 'dhelp-page', method=method, doc=doc ) ]
