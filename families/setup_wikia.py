"""Sample Pywikibot family package."""
import sys

from setuptools import setup

family_package_name = 'wikia'

setup(
    name='PywikibotWikiaFamily',
    version='0.1',
    description='Wikia configuration for Pywikibot',
    long_description='Wikia configuration for Pywikibot',
    maintainer='The Pywikibot team',
    maintainer_email='pywikibot@lists.wikimedia.org',
    license='MIT License',
    packages=['pywikibot', 'pywikibot.families.' + family_package_name],
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
