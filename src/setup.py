#!/usr/bin/python
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

from setuptools import setup, find_packages

setup(
    name='spacewalk-splice-tool',
    version='0.1',
    license='GPLv2+',
    author='Pradeep Kilambi',
    author_email='pkilambi@redhat.com',
    description='A tool for gathering active system checkin data from spacewalk server and report to Splice server',
    url='https://github.com/splice/spacewalk-splice-tool.git',
    packages=find_packages(),
)
