"""Sample Pywikibot family package."""
import sys

from setuptools import setup

family_package_name = 'wikia'
family_modules = ['lyricwiki']

py_modules = ['pywikibot.families.%s.%s_family'
              % (family_package_name, module)
              for module in family_modules]

if sys.version_info[0] < 3:
    py_modules += ['pywikibot.__init__']

setup(
    name='PywikibotWikiaFamily',
    version='0.1',
    description='Wikia configuration for Pywikibot',
    long_description='Wikia configuration for Pywikibot',
    maintainer='The Pywikibot team',
    maintainer_email='pywikibot@lists.wikimedia.org',
    license='MIT License',
    py_modules=py_modules,
    install_requires='pywikibot',
    url='https://www.mediawiki.org/wiki/Pywikibot',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Development Status :: 4 - Beta',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers',
        'Environment :: Console',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
    ],
    use_2to3=False,
    zip_safe=False
)
