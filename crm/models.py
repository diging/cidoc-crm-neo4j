"""
Dynamic implementation of the CRM.

On import, will run :func:`.build_model` to populate the namespace with
non-abstract hierarchial subclasses of  :class:`.HeritableStructuredNode`\.

Example
-------

.. code-block:: python

   >>> from neomodel import config
   >>> config.DATABASE_URL = 'bolt://neo4j:neo4j@localhost:7687'
   >>> from crm import models
   >>> models.build_model("http://.....path/to/schema.rdfs.xml")
   >>> joe = model.E21Person(value='Joe Bloggs')
   >>> joe.save()
   <E21Person: {'id': 33, 'value': 'Joe Bloggs'}>

   >>> tempe = model.E53Place(value='Tempe, Arizona')
   >>> tempe.save()
   <E53Place: {'id': 34, 'value': 'Tempe, Arizona'}>

   >>> joe.P74_has_current_or_former_residence.connect(tempe)
   <neomodel.relationship.P74HasCurrentOrFormerResidence at 0x109800250>

"""

from neomodel import StructuredNode, StringProperty, RelationshipTo, StructuredRel
import sys
from collections import defaultdict

from crm.load import import_schema


class HeritableStructuredNode(StructuredNode):
    """
    Extends :class:`neomodel.StructuredNode` to provide the :meth:`.downcast`
    method.
    """
    __abstract_node__ = True

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


def get_or_create_rel_class(identifier, entry, classdata, propdata, sources):
    _globs = globals()
    if identifier in _globs:
        return _globs[identifier]

    params = {
        '__doc__': entry.get('comment', ""),
        'display_label': entry.get('label', identifier),
        'code': entry.get('code'),
        'value': StringProperty(),
        'safe_name': entry.get('safe_name')
    }
    return type(str(identifier), (StructuredRel,), params)


def get_or_create_class(identifier, entry, classdata, propdata, sources):
    _globs = globals()
    if identifier in _globs:
        return _globs[identifier]

    if entry.get('subClassOf'):
        super_identifiers = entry.get('subClassOf')
        superClasses = tuple([get_or_create_class(ident, classdata[ident], classdata, propdata, sources) for ident in super_identifiers])
    else:
        superClasses = (HeritableStructuredNode,)

    params = {
        '__doc__': entry.get('comment', ""),
        'display_label': entry.get('label'),
        'value': StringProperty(),
        'code': entry.get('code'),
        'safe_name': entry.get('safe_name')
    }

    property_identifiers = sources.get(identifier, [])
    for ident in property_identifiers:
        prop = propdata.get(ident)
        target_identifier = prop.get('range')
        rel = RelationshipTo(target_identifier, ident,
                             model=get_or_create_rel_class(ident, prop, classdata, propdata, sources))
        params[prop.get('safe_name')] = rel

    _globs[identifier] = type(str(identifier), superClasses, params)
    return _globs[identifier]


def build_model(schema_url):
    """
    Populate the current namespace with the CRM.
    """
    classdata, propdata = import_schema(schema_url)

    sources = defaultdict(list)
    for prop, entry in propdata.items():
        sources[entry.get('domain')].append(prop)

    for ident, entry in classdata.items():
        get_or_create_class(ident, entry, classdata, propdata, sources)
    for ident, entry in propdata.items():
        get_or_create_rel_class(ident, entry, classdata, propdata, sources)
