"""
Methods for parsing the CIDOC CRM RDF specification into something useful.
"""

import rdflib
from rdflib.term import URIRef
from itertools import chain

TITLE = URIRef('http://purl.org/dc/terms/title')
PROPERTY = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#Property')
TYPE = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
CLASS = URIRef('http://www.w3.org/2000/01/rdf-schema#Class')
OWL_CLASS = URIRef('http://www.w3.org/2002/07/owl#Class')
DESCRIPTION = URIRef('http://purl.org/dc/terms/description')
COMMENT = URIRef('http://www.w3.org/2000/01/rdf-schema#comment')

LABEL = URIRef('http://www.w3.org/2000/01/rdf-schema#label')
RANGE = URIRef('http://www.w3.org/2000/01/rdf-schema#range')
DOMAIN = URIRef('http://www.w3.org/2000/01/rdf-schema#domain')
SUBPROPERTYOF = URIRef('http://www.w3.org/2000/01/rdf-schema#subPropertyOf')
SUBCLASSOF = URIRef('http://www.w3.org/2000/01/rdf-schema#subClassOf')


def _get_object(g, s, p):
    """
    Retrieve the (first) object of a relation. This is mainly to be used where
    we expect only one relation of the specified type.

    Parameters
    ----------
    g : rdflib.Graph
    s : rdflib.term.URIRef
        The subject of the relation.
    p : rdflib.term.URIRef
        The predicate of the relation.

    Returns
    -------
    rdflib.term.URIRef
    """

    # objects() will return an empty iterator if the predicate is not found.
    try:
        return list(g.objects(s, p))[0]
    except IndexError:
        return None


def _get_label(g, s):
    """
    Try to find the English label. Short of that, choose the first label.
    """
    try:
        for label in g.objects(s, LABEL):
            if label.language == 'en':
                return label
        return list(g.objects(s, LABEL))[0]
    except IndexError:
        return _identifier(s)


def _identifier(uri_ref):
    """
    Grab the identifier from a URIRef.

    Parameters
    ----------
    uri_ref : rdflib.term.URIRef

    Returns
    -------
    unicode
    """
    if '#' in uri_ref:
        delim = '#'
    else:
        delim = '/'
    ident_parts = unicode(uri_ref).split(delim)[-1].split('_')
    # Can you think of a hackier way to do this? I can't.
    return ' '.join(ident_parts).title().replace(' ', '').replace('-', ''), \
            '_'.join(ident_parts).replace('-', '_'), ident_parts[0]


def import_schema(schema_url):
    """
    (Down)load, parse, and deconstruct an RDF/XML schema.

    Parameters
    ---------
    schema_url : str
        This gets passed on to :meth:`rdflib.Graph.parse`\. So anything valid
        as a source for that method will suffice.

    Returns
    -------
    :class:`dict`
        Keys are identifiers, values class descriptions.
    :class:`dict`
        Keys are identifiers, values are property (relation) descriptions.
    """

    # TODO: this was ported from another project; it can probably be refactored
    #  or at least tidied for clarity.
    g = rdflib.Graph()
    # Load RDF from remote location.
    try:
        g.parse(schema_url)
    except:
        g.parse(schema_url, format='xml')

    # Literal is an RDFClass, too! At least it's easier, that way.
    literal_instance = {'identifier': u'Literal', 'label': u'Literal'}

    # Some schemas use the OWL Class type.
    classes = chain(g.subjects(TYPE, CLASS), g.subjects(TYPE, OWL_CLASS))
    properties = g.subjects(TYPE, PROPERTY)

    subClass_relations, subProperty_relations = [], []
    classesHash = {}
    propertiesHash = {}
    codeHash = {}

    # We index the Literal RDFClass so that we can retrieve it when populating
    #  domain and range fields on RDFProperty instances.
    classesHash[u'Literal'] = literal_instance

    # Build RDFClasses first, so that we can use them in the domain and range
    #  of RDFProperty instances.
    for class_ref in classes:
        identifier, safe_name, code  = _identifier(class_ref)

        # We prefer to use the description, but comment is fine, too.
        comment = _get_object(g, class_ref, DESCRIPTION)
        if not comment:
            comment = _get_object(g, class_ref, COMMENT)

        kwargs = {
            'identifier': identifier,
            'code': code,
            'safe_name': safe_name,
            'comment': comment.toPython() if comment is not None else None,
            'label': _get_label(g, class_ref).toPython(),
            'subClassOf': []
        }
        classesHash[identifier] = kwargs

        # We defer filling subClassOf on the model instances until after we have
        #  created all of the instances.
        # subClassOf = _get_object(g, class_ref, SUBCLASSOF)
        subClassOf = list(g.objects(class_ref, SUBCLASSOF))
        if subClassOf:
            for superClass in subClassOf:
                subClass_relations.append((identifier, _identifier(superClass)[0]))

    # Fill in subClass relations on the model instances.
    for source, target in subClass_relations:
        classesHash[source]['subClassOf'].append(classesHash[target]['identifier'])

    # Now generate RDFProperty instances.
    for property_ref in properties:
        identifier, safe_name, code = _identifier(property_ref)
        if code.endswith('i'):    # It's a bit of a waste to add inverse relations.
            continue

        # We prefer to use the description, but comment is fine, too.
        comment = _get_object(g, property_ref, DESCRIPTION)
        if not comment:
            comment = _get_object(g, property_ref, COMMENT)

        kwargs = {
            'identifier': identifier,
            'code': code,
            'safe_name': safe_name,
            'comment': comment.toPython() if comment is not None else None,
            'label': _get_label(g, property_ref).toPython(),
        }
        kwargs['domain'] = _identifier(_get_object(g, property_ref, DOMAIN))[0]
        codeHash[code] = identifier
        try:
            range_ref = _get_object(g, property_ref, RANGE)
            rclass = classesHash[_identifier(range_ref)[0]]
        except KeyError:
            rclass = {
                'identifier': _identifier(range_ref)[0],
            }
            classesHash[_identifier(range_ref)[0]] = rclass
        kwargs['range'] = rclass['identifier']
        propertiesHash[identifier] = kwargs

        # We defer filling subPropertyOf on the model instances until after we
        #  have created all of the instances.
        subPropertyOf = _get_object(g, class_ref, SUBPROPERTYOF)
        if subPropertyOf:
            subProperty_relations.append((identifier, _identifier(subPropertyOf)[0]))

    # Fill in the subPropertyOf field on RDFProperty instances.
    for source, target in subProperty_relations:
        propertiesHash[source]['subPropertyOf'] = propertiesHash[target]['identifier']
    return classesHash, propertiesHash
