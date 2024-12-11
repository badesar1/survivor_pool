# poolapp/templatetags/form_tags.py

from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    """
    Adds the specified CSS class to a form field.
    Usage: {{ form.field_name|add_class:"css-class-name" }}
    """
    return field.as_widget(attrs={"class": css})

