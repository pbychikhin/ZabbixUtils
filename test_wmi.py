import wmi

wobj = wmi.WMI(namespace="root/WebAdministration")
counter = 0
for site in wobj.instances("Site"):
    print(counter, site.Name)
    for binding in site.Bindings:
        print("   for the protocol {} have the binding info {}".format(binding.protocol, binding.BindingInformation))
    counter += 1