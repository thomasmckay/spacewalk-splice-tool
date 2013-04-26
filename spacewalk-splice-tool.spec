# spacewalk-splice-tool package
Name:           spacewalk-splice-tool
Version:        0.11
Release:        1%{?dist}
Summary:        A tool for gathering active system checkin data from spacewalk server and report to Splice server

Group:          Development/Languages
License:        GPLv2+
URL:        https://github.com/splice/spacewalk-splice-tool
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python-setuptools
BuildRequires:  python2-devel

Requires: python-certutils
Requires: python-oauth2
Requires: subscription-manager-migration-data
Requires: splice-common >= 0.77
Requires: /usr/sbin/crond

%description
A tool for gathering system checkin data from spacewalk server and report to Splice server

%prep
%setup -q

%build
pushd src
%{__python} setup.py build
popd


%install
rm -rf %{buildroot}
pushd src
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
popd
mkdir -p %{buildroot}/%{_sysconfdir}/sysconfig/
mkdir -p %{buildroot}/%{_sysconfdir}/splice/
mkdir -p %{buildroot}/%{_bindir}
mkdir -p %{buildroot}/%{_var}/log/%{name}
mkdir -p %{buildroot}/%{_sysconfdir}/cron.d
mkdir -p %{buildroot}/%{_datadir}/spacewalk/reports/data/

# Configuration
cp -R etc/splice/* %{buildroot}/%{_sysconfdir}/splice/
cp -R etc/cron.d/* %{buildroot}/%{_sysconfdir}/cron.d/
cp etc/sysconfig/spacewalk-sst-sync %{buildroot}/%{_sysconfdir}/sysconfig/

# Tools
cp bin/* %{buildroot}/%{_bindir}/
cp scripts/cp-export %{buildroot}/%{_datadir}/spacewalk/reports/data/

# Remove egg info
rm -rf %{buildroot}/%{python_sitelib}/*.egg-info

%clean
rm -rf %{buildroot}

%post
/sbin/service crond condrestart

%postun
/sbin/service crond condrestart

%files
%defattr(-,root,root,-)
%attr(755,root,root) %{_bindir}/spacewalk-splice-checkin
%attr(755,root,root) %{_bindir}/spacewalk-sst-sync
%{python_sitelib}/spacewalk_splice_tool*
%config(noreplace) %{_sysconfdir}/splice/checkin.conf
%config(noreplace) %{_sysconfdir}/sysconfig/spacewalk-sst-sync
%config(noreplace) %attr(644,root,root) %{_sysconfdir}/cron.d/spacewalk-sst-sync
%config(noreplace) %attr(644,root,root) %{_sysconfdir}/cron.d/splice-sst-sync
%attr(644,root,root) %{_datadir}/spacewalk/reports/data/cp-export
%doc LICENSE

%changelog
* Tue Apr 16 2013 John Matthews <jwmatthews@gmail.com> 0.11-1
- Added a CLI option: --sample-json if set to a path we will output the json
  data we send to Splice as separate files (jwmatthews@gmail.com)
- Added rhic-serve-common dep to spec file (jwmatthews@gmail.com)
- default to one socket, instead of blank (cduryee@redhat.com)
- populate org id and name in mpu (cduryee@redhat.com)

* Thu Apr 11 2013 John Matthews <jwmatthews@gmail.com> 0.10-1
- Automatic commit of package [spacewalk-splice-tool] release [0.9-1].
  (jwmatthews@gmail.com)
- Upload Pool/Product/Rules data to splice.common.api during 'checkin' run
  (jwmatthews@gmail.com)
- config cleanup, and removal of some dead code (cduryee@redhat.com)

* Thu Apr 11 2013 John Matthews <jwmatthews@gmail.com> 0.9-1
- Upload Pool/Product/Rules data to splice.common.api during 'checkin' run
  (jwmatthews@gmail.com)
- use oauth instead of username/pass (cduryee@redhat.com)
- spec updates (cduryee@redhat.com)
- delete systems from candlepin that were deleted in spacewalk
  (cduryee@redhat.com)
- do not allow two instances of sst to run at once (cduryee@redhat.com)
- use org ID instead of org name, and clean up logging statements
  (cduryee@redhat.com)
- Read data out of spacewalk DB instead of using APIs (cduryee@redhat.com)
- Use all systems in spacewalk, do not perform group to rhic mapping
  (cduryee@redhat.com)
- add entitlementStatus to MPU (cduryee@redhat.com)
- use qty of the entitlement, not the pool (cduryee@redhat.com)
- send candlepin data to rcs (cduryee@redhat.com)
- set facts in a way that candlepin expects (cduryee@redhat.com)
- candlepin support (cduryee@redhat.com)
- candlepin support (cduryee@redhat.com)

* Fri Feb 01 2013 John Matthews <jwmatthews@gmail.com> 0.8-1
- Change default num sockets to 0 if no data is available
  (jwmatthews@gmail.com)

* Thu Jan 31 2013 John Matthews <jwmatthews@gmail.com> 0.7-1
- Update to handle errors and display error messages from remote server
  (jwmatthews@gmail.com)

* Wed Jan 30 2013 John Matthews <jmatthews@redhat.com> 0.6-1
- Added support for "inactive" systems (jmatthews@redhat.com)
- Update for new location of certs (jmatthews@redhat.com)
- send server metadata before product usage (cduryee@redhat.com)
- find root for cloned channels when calculating product usage
  (cduryee@redhat.com)
- additional debugging, and clone mapping POC (cduryee@redhat.com)
- changes for socket support (wip) (cduryee@redhat.com)
- fixing facts data to match what report server expects (pkilambi@redhat.com)

* Wed Oct 31 2012 Pradeep Kilambi <pkilambi@redhat.com> 0.5-1
- using local config to avoid django interference (pkilambi@redhat.com)

* Wed Oct 31 2012 Pradeep Kilambi <pkilambi@redhat.com> 0.4-1
- requiring current version of splice-common for compatibility
  (pkilambi@redhat.com)

* Wed Oct 31 2012 Pradeep Kilambi <pkilambi@redhat.com> 0.3-1
- Add logging support (pkilambi@redhat.com)
- Adding requires on splice-common (pkilambi@redhat.com)
- updating cron info and added a note if user wants to update the crontab
  (pkilambi@redhat.com)
- adding support to upload product usage (pkilambi@redhat.com)
- adding rel-eng dir (pkilambi@redhat.com)
- updating spec file (pkilambi@redhat.com)

* Mon Oct 29 2012 Pradeep Kilambi <pkilambi@redhat.com> 0.2-1
- new package built with tito

