"""
Dynamic implementation of the CRM.

Use :func:`.build_model` to populate the namespace with non-abstract hierarchial
subclasses of  :class:`.HeritableStructuredNode`\.

Example
-------

.. code-block:: python

   >>> from neomodel import config
   >>> config.DATABASE_URL = 'bolt://neo4j:neo4j@localhost:7687'
   >>> from crm import models
   >>> models.build_models("http://.....path/to/schema.rdfs.xml")
   >>> joe = model.E21Person(value='Joe Bloggs')
   >>> joe.save()
   <E21Person: {'id': 33, 'value': 'Joe Bloggs'}>

   >>> tempe = model.E53Place(value='Tempe, Arizona')
   >>> tempe.save()
   <E53Place: {'id': 34, 'value': 'Tempe, Arizona'}>

   >>> joe.P74_has_current_or_former_residence.connect(tempe)
   <neomodel.relationship.P74HasCurrentOrFormerResidence at 0x109800250>

"""


import neomodel
import sys
from collections import defaultdict

from crm.load import import_schema


class HeritableStructuredNode(neomodel.StructuredNode):
    """
    Extends :class:`neomodel.StructuredNode` to provide the :meth:`.downcast`
    method.
    """
    __abstract_node__ = True

    def primary_label(self):
        _get_class = lambda cname: getattr(sys.modules[__name__], cname)
        # inherited_labels() only returns the labels for the current class and
        #  any super-classes, whereas labels() will return all labels on the
        #  node.
        classes = list(set(self.labels()) - set(self.inherited_labels()))
        if len(classes) == 0:          # The most derivative class is already
            return self.__class__.__name__       #  instantiated.
        elif len(classes) == 1:    # Only one option, so this must be it.
            return classes[0]
        else:    # Infer the most derivative class by looking for the one
                 #  with the longest method resolution order.
            class_objs = map(_get_class, classes)
            _, cls = sorted(zip(map(lambda cls: len(cls.mro()),
                                    class_objs),
                                class_objs),
                            key=lambda (size, cls): size)[-1]
            return cls.__name__


    def upcast(self, target_class):
        """
        Re-instantiate this node as an instance of a more abstract class.
        """

        if not isinstance(target_class, basestring):
            # In the spirit of neomodel, we might as well support both
            #  class (type) objects and class names as targets.
            target_class = target_class.__name__

        if target_class not in self.inherited_labels():
            raise ValueError('%s is not a super-class of %s'\
                             % (target_class, self.__class__.__name__))

        cls = getattr(sys.modules[__name__], target_class)
        instance = cls.inflate(self.id)

        # TODO: Can we re-instatiate without hitting the database again?
        instance.refresh()
        return instance

    def downcast(self, target_class=None):
        """
        Re-instantiate this node as an instance its most derived derived class.
        """
        # TODO: there is probably a far more robust way to do this.
        _get_class = lambda cname: getattr(sys.modules[__name__], cname)

        # inherited_labels() only returns the labels for the current class and
        #  any super-classes, whereas labels() will return all labels on the
        #  node.
        classes = list(set(self.labels()) - set(self.inherited_labels()))

        if len(classes) == 0:
            return self     # The most derivative class is already instantiated.
        cls = None

        if target_class is None:    # Caller has not specified the target.
            if len(classes) == 1:    # Only one option, so this must be it.
                target_class = classes[0]
            else:    # Infer the most derivative class by looking for the one
                     #  with the longest method resolution order.
                class_objs = map(_get_class, classes)
                _, cls = sorted(zip(map(lambda cls: len(cls.mro()),
                                        class_objs),
                                    class_objs),
                                key=lambda (size, cls): size)[-1]
        else:    # Caller has specified a target class.
            if not isinstance(target_class, basestring):
                # In the spirit of neomodel, we might as well support both
                #  class (type) objects and class names as targets.
                target_class = target_class.__name__

            if target_class not in classes:
                raise ValueError('%s is not a sub-class of %s'\
                                 % (target_class, self.__class__.__name__))
        if cls is None:
            cls = getattr(sys.modules[__name__], target_class)
        instance = cls.inflate(self.id)

        # TODO: Can we re-instatiate without hitting the database again?
        instance.refresh()
        return instance


def get_or_create_rel_class(identifier, entry, fields={}):
    """
    Get a property (relation) class from the current namespace, or construct
    and register one.

    Parameters
    ----------
    identifier : str
        Unique name of the class.
    entry : dict
        Metadata for the class. Expects (but does not require) keys ``comment``,
        ``label``, ``code``, and ``safe_name``.
    fields : dict
        (optional) Specify extra fields to add to the class specification.
        Keys should be valid property names, and values should be callables
        that return :class:`neomodel.properties.Property` instances.

    Returns
    -------
    :class:`type`
    """
    _globs = globals()
    if identifier in _globs:
        return _globs[identifier]

    params = {
        '__doc__': entry.get('comment', ""),
        'description': entry.get('comment', ""),
        'display_label': entry.get('label', identifier),
        'code': entry.get('code'),
        'safe_name': entry.get('safe_name'),
        'range': entry.get('range')
    }

    for key, val in fields.items():
        # TODO: ensure that ``key`` is a valid property name.
        if hasattr(val, '__call__') and key not in params:
            val = val()
            if not isinstance(val, neomodel.properties.Property):
                continue
            params[key] = val

    _globs[identifier] = type(str(identifier), (neomodel.StructuredRel,), params)
    return _globs[identifier]


def get_or_create_class(identifier, entry, classdata, propdata, sources,
                        fields={}, rel_fields={}):
    """
    Get a class from the current namspace, or create and register one.

    Parameters
    ----------
    identifier : str
        Unique name of the class.
    entry : dict
        Metadata for the class. Expects (but does not require) keys ``comment``,
        ``label``, ``code``, and ``safe_name``.
    classdata : dict
        All raw metadata for the classes in this schema, keyed on identifier.
    propdata : dict
        All raw metadata for the properties (relations) in this schema, keyed
        on identifier.
    sources : dict
        Hashtable containing (values) a list of property identifiers that
        belong to each class identifier (keys).
    fields : dict
        (optional) Specify extra fields to add to the class specification.
        Keys should be valid property names, and values should be callables
        that return :class:`neomodel.properties.Property` instances.
    rel_fields : dict
        (optional) Specify extra fields to add to linked relation class
        specifications. Keys should be valid property names, and values should
        be callables that return :class:`neomodel.properties.Property`
        instances.

    Returns
    -------
    :class:`type`
    """
    _globs = globals()
    if identifier in _globs:
        return _globs[identifier]

    if entry.get('subClassOf'):
        super_identifiers = entry.get('subClassOf')
        superClasses = tuple([get_or_create_class(ident, classdata[ident],
                                                  classdata, propdata, sources,
                                                  fields=fields,
                                                  rel_fields=rel_fields)
                              for ident in super_identifiers])
    else:
        superClasses = (HeritableStructuredNode,)

    params = {
        '__doc__': entry.get('comment', ""),
        'description': entry.get('comment', ""),
        'display_label': entry.get('label'),
        'code': entry.get('code'),
        'safe_name': entry.get('safe_name')
    }
    for key, val in fields.items():
        # TODO: ensure that ``key`` is a valid property name.
        if hasattr(val, '__call__') and key not in params:
            val = val()
            if not isinstance(val, neomodel.properties.Property):
                continue
            params[key] = val

    property_identifiers = sources.get(identifier, [])
    for ident in property_identifiers:
        prop = propdata.get(ident)
        target_identifier = prop.get('range')
        target_class = get_or_create_rel_class(ident, prop, fields=rel_fields)
        rel = neomodel.RelationshipTo(target_identifier, ident,
                                      model=target_class)
        params[prop.get('safe_name')] = rel

    _globs[identifier] = type(str(identifier), superClasses, params)
    return _globs[identifier]


def build_models(schema_url, fields={}, rel_fields={}):
    """
    Populate the current namespace with the CRM.

    Parameters
    ---------
    schema_url : str
        This gets passed on to :meth:`rdflib.Graph.parse`\. So anything valid
        as a source for that method will suffice.
    fields : dict
        (optional) Specify extra fields to add to class specifications.
        Keys should be valid property names, and values should be callables
        that return :class:`neomodel.properties.Property` instances.
    rel_fields : dict
        (optional) Specify extra fields to add to relation class
        specifications. Keys should be valid property names, and values should
        be callables that return :class:`neomodel.properties.Property`
        instances.
    """
    classdata, propdata = import_schema(schema_url)

    sources = defaultdict(list)
    for prop, entry in propdata.items():
        sources[entry.get('domain')].append(prop)

    for ident, entry in classdata.items():
        get_or_create_class(ident, entry, classdata, propdata, sources,
                            fields=fields, rel_fields=rel_fields)
    for ident, entry in propdata.items():
        get_or_create_rel_class(ident, entry, fields=rel_fields)
