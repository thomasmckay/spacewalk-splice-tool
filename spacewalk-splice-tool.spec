# spacewalk-splice-tool package
Name:           spacewalk-splice-tool
Version:        0.2
Release:        1%{?dist}
Summary:        A tool for gathering active system checkin data from spacewalk server and report to Splice server

Group:          Development/Languages
License:        GPLv2+
URL:        https://github.com/splice/spacewalk-splice-tool
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python-setuptools
BuildRequires:  python2-devel

Requires: python-certutils
Requires: subscription-manager-migration-data
Requires: /usr/sbin/crond

%description
A tool for gathering active system checkin data from spacewalk server and report to Splice server

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
mkdir -p %{buildroot}/%{_sysconfdir}/rhn/splice/
mkdir -p %{buildroot}/%{_usr}/%{_bindir}
mkdir -p %{buildroot}/%{_var}/log/%{name}
mkdir -p %{buildroot}/%{_sysconfdir}/cron.d

# Configuration
cp -R etc/rhn/splice/* %{buildroot}/%{_sysconfdir}/rhn/splice/
cp scripts/spacewalk-splice-tool.cron %{buildroot}/%{_sysconfdir}/cron.d/

# Tools
cp bin/* %{buildroot}/%{_usr}/%{_bindir}/

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
%{python_sitelib}/spacewalk_splice_tool*

%config(noreplace) %attr(644,root,root) %{cron_dir}/spacewalk-splice-tool.cron
%doc LICENSE

%changelog
* Mon Oct 29 2012 Pradeep Kilambi <pkilambi@redhat.com> 0.2-1
- new package built with tito

