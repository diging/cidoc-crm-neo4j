from setuptools import setup, Extension

DISTNAME = 'crm4j'
AUTHOR = 'Erick Peirson'
MAINTAINER = 'Erick Peirson'
MAINTAINER_EMAIL = 'erick.peirson@gmail.com'
DESCRIPTION = 'Meta-implementation of the CIDOC-CRM for Neo4j, using neomodel'
LICENSE = 'GNU GPL 3'
URL = ''
VERSION = '0.1'

PACKAGES = ['crm']

setup(
    name=DISTNAME,
    author=AUTHOR,
    maintainer=MAINTAINER,
    maintainer_email=MAINTAINER_EMAIL,
    description=DESCRIPTION,
    license=LICENSE,
    url=URL,
    version=VERSION,
    packages = PACKAGES,
    include_package_data=True,
    install_requires=[
        "appdirs==1.4.3",
        "isodate==0.5.4",
        "neo4j-driver==1.1.0",
        "neomodel==3.2.2",
        "packaging==16.8",
        "pyparsing==2.2.0",
        "pytz==2017.2",
        "rdflib==4.2.2",
        "six==1.10.0"
    ]
)
