from jinja2 import FileSystemLoader, Environment
import os
import inspect

def get_rendered(template_filename, **values):
    frm = inspect.stack()[1]
    mod = inspect.getmodule(frm[0])
    templates_path = os.path.join(os.path.dirname(mod.__file__), "templates")
    env = Environment(loader=FileSystemLoader(templates_path), autoescape=True)
    tmpl = env.get_template(template_filename)
    return tmpl.render(**values)
