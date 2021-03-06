from django.core.urlresolvers import reverse  # noqa
from django import http
from mox import IsA  # noqa

from openstack_dashboard import api
from openstack_dashboard.test import helpers as test

from novaclient.v1_1 import flavors

from openstack_dashboard.dashboards.admin.flavors import workflows

INDEX_URL = reverse('horizon:admin:flavors:index')


class FlavorsViewTests(test.BaseAdminViewTests):
    @test.create_stubs({api.nova: ('flavor_list',), })
    def test_index(self):
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())
        self.mox.ReplayAll()

        res = self.client.get(INDEX_URL)
        self.assertTemplateUsed(res, 'admin/flavors/index.html')
        self.assertItemsEqual(res.context['table'].data, self.flavors.list())


class BaseFlavorWorkflowTests(test.BaseAdminViewTests):
    def _flavor_create_params(self, flavor, id=None):
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        flavor_info = {"name": flavor.name,
                       "vcpu": flavor.vcpus,
                       "memory": flavor.ram,
                       "disk": flavor.disk,
                       "swap": flavor.swap,
                       "ephemeral": eph,
                       "is_public": flavor.is_public}
        if id:
            flavor_info["flavorid"] = id
        return flavor_info

    def _get_workflow_fields(self, flavor, id=None, access=None):
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        flavor_info = {"name": flavor.name,
                       "vcpus": flavor.vcpus,
                       "memory_mb": flavor.ram,
                       "disk_gb": flavor.disk,
                       "swap_mb": flavor.swap,
                       "eph_gb": eph}
        if access:
            access_field_name = 'update_flavor_access_role_member'
            flavor_info[access_field_name] = [p.id for p in access]
        if id:
            flavor_info['flavor_id'] = id
        return flavor_info

    def _get_workflow_data(self, flavor, id=None, access=None):
        flavor_info = self._get_workflow_fields(flavor, access=access,
                                                id=id)
        return flavor_info


class CreateFlavorWorkflowTests(BaseFlavorWorkflowTests):
    @test.create_stubs({api.keystone: ('tenant_list',), })
    def test_workflow_get(self):
        projects = self.tenants.list()

        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        self.mox.ReplayAll()

        url = reverse('horizon:admin:flavors:create')
        res = self.client.get(url)
        self.assertTemplateUsed(res, 'admin/flavors/create.html')
        workflow = res.context['workflow']
        expected_name = workflows.CreateFlavor.name
        self.assertEqual(res.context['workflow'].name, expected_name)
        self.assertQuerysetEqual(workflow.steps,
                            ['<CreateFlavorInfo: createflavorinfoaction>',
                             '<UpdateFlavorAccess: update_flavor_access>'])

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',
                                   'flavor_create',)})
    def test_create_flavor_without_projects_post(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn([])

        # handle
        params = self._flavor_create_params(flavor, id='auto')
        api.nova.flavor_create(IsA(http.HttpRequest), **params) \
                .AndReturn(flavor)

        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor)

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertNoFormErrors(res)
        self.assertRedirectsNoFollow(res, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',
                                   'flavor_create',
                                   'add_tenant_to_flavor',)})
    def test_create_flavor_with_projects_post(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn([])

        # handle
        params = self._flavor_create_params(flavor, id='auto')
        params['is_public'] = False
        api.nova.flavor_create(IsA(http.HttpRequest), **params) \
                .AndReturn(flavor)
        for project in projects:
            api.nova.add_tenant_to_flavor(IsA(http.HttpRequest),
                                          flavor.id, project.id)
        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor, access=projects)

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertNoFormErrors(res)
        self.assertRedirectsNoFollow(res, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',)})
    def test_create_existing_flavor_name_error(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])

        # handle
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn(self.flavors.list())
        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor)

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertFormErrors(res)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',)})
    def test_create_existing_flavor_id_error(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])

        # handle
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn(self.flavors.list())
        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor)
        # Name is okay.
        workflow_data['name'] = 'newflavorname'
        # Flavor id already exists.
        workflow_data['flavor_id'] = flavor.id

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertFormErrors(res)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',
                                   'flavor_create',
                                   'add_tenant_to_flavor',)})
    def test_create_flavor_project_update_error(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn([])

        # handle
        params = self._flavor_create_params(flavor, id='auto')
        params['is_public'] = False
        api.nova.flavor_create(IsA(http.HttpRequest), **params) \
                .AndReturn(flavor)
        for project in projects:
            expect = api.nova.add_tenant_to_flavor(IsA(http.HttpRequest),
                                                   flavor.id, project.id)
            if project == projects[0]:
                expect.AndRaise(self.exceptions.nova)
        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor, access=projects)

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertNoFormErrors(res)
        self.assertMessageCount(error=1, warning=0)
        self.assertRedirectsNoFollow(res, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_list',)})
    def test_create_flavor_missing_field_error(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()

        # init
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn([])
        self.mox.ReplayAll()

        workflow_data = self._get_workflow_data(flavor)
        workflow_data["name"] = ""

        url = reverse('horizon:admin:flavors:create')
        res = self.client.post(url, workflow_data)

        self.assertFormErrors(res)
        self.assertContains(res, "field is required")


class UpdateFlavorWorkflowTests(BaseFlavorWorkflowTests):
    @test.create_stubs({api.nova: ('flavor_get',
                                   'flavor_access_list',),
                        api.keystone: ('tenant_list',)})
    def test_update_flavor_get(self):
        flavor = self.flavors.list()[2]
        flavor_access = self.flavor_access.list()
        projects = self.tenants.list()

        # GET/init, set up expected behavior
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)).AndReturn([projects,
                                                                   False])
        api.nova.flavor_access_list(IsA(http.HttpRequest), flavor.id) \
                .AndReturn(flavor_access)

        # Put all mocks created by mox into replay mode
        self.mox.ReplayAll()

        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        res = self.client.get(url)

        self.assertTemplateUsed(res, 'admin/flavors/update.html')

        workflow = res.context['workflow']
        expected_name = workflows.UpdateFlavor.name
        self.assertEqual(res.context['workflow'].name, expected_name)

        self.assertQuerysetEqual(workflow.steps,
                            ['<UpdateFlavorInfo: update_info>',
                             '<UpdateFlavorAccess: update_flavor_access>'])

        step = workflow.get_step("update_info")
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        self.assertEqual(step.action.initial['name'], flavor.name)
        self.assertEqual(step.action.initial['vcpus'], flavor.vcpus)
        self.assertEqual(step.action.initial['memory_mb'], flavor.ram)
        self.assertEqual(step.action.initial['disk_gb'], flavor.disk)
        self.assertEqual(step.action.initial['swap_mb'], flavor.swap)
        self.assertEqual(step.action.initial['eph_gb'], eph)

        step = workflow.get_step("update_flavor_access")
        field_name = step.get_member_field_name('member')
        self.assertEqual(step.action.fields[field_name].initial,
                         [fa.tenant_id for fa in flavor_access])

    @test.create_stubs({api.nova: ('flavor_get',), })
    def test_update_flavor_get_flavor_error(self):
        flavor = self.flavors.first()

        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .AndRaise(self.exceptions.nova)

        self.mox.ReplayAll()

        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        res = self.client.get(url)

        self.assertRedirectsNoFollow(res, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_get_extras',
                                   'flavor_list',
                                   'flavor_delete',
                                   'flavor_create')})
    def test_update_flavor_without_extra_specs(self):
        # The first element has no extra specs
        flavor = self.flavors.first()
        projects = self.tenants.list()
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        extra_specs = getattr(flavor, 'extra_specs')
        new_flavor = flavors.Flavor(flavors.FlavorManager(None),
                                    {'id':
                                     "cccccccc-cccc-cccc-cccc-cccccccccccc",
                                     'name': flavor.name,
                                     'vcpus': flavor.vcpus + 1,
                                     'disk': flavor.disk,
                                     'ram': flavor.ram,
                                     'swap': 0,
                                     'OS-FLV-EXT-DATA:ephemeral': eph,
                                     'extra_specs': extra_specs})

        # GET/init, set up expected behavior
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())

        # POST/init
        api.nova.flavor_get_extras(IsA(http.HttpRequest),
                                   flavor.id, raw=True) \
                                   .AndReturn(extra_specs)
        api.nova.flavor_delete(IsA(http.HttpRequest), flavor.id)
        api.nova.flavor_create(IsA(http.HttpRequest),
                               new_flavor.name,
                               new_flavor.ram,
                               new_flavor.vcpus,
                               new_flavor.disk,
                               swap=new_flavor.swap,
                               ephemeral=eph,
                               flavorid=flavor.id,
                               is_public=True).AndReturn(new_flavor)

        # Put mocks in replay mode
        self.mox.ReplayAll()

        # run get test
        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        # run post test
        workflow_data = {'flavor_id': flavor.id,
                         'name': new_flavor.name,
                         'vcpus': new_flavor.vcpus,
                         'memory_mb': new_flavor.ram,
                         'disk_gb': new_flavor.disk,
                         'swap_mb': new_flavor.swap,
                         'eph_gb': eph,
                         'is_public': True}
        resp = self.client.post(url, workflow_data)
        self.assertNoFormErrors(resp)
        self.assertMessageCount(success=1)
        self.assertRedirectsNoFollow(resp, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_get_extras',
                                   'flavor_list',
                                   'flavor_delete',
                                   'flavor_create',
                                   'flavor_extra_set')})
    def test_update_flavor_with_extra_specs(self):
        # The second element has extra specs
        flavor = self.flavors.list()[1]
        projects = self.tenants.list()
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        extra_specs = getattr(flavor, 'extra_specs')
        new_flavor = flavors.Flavor(flavors.FlavorManager(None),
                                    {'id':
                                     "cccccccc-cccc-cccc-cccc-cccccccccccc",
                                    'name': flavor.name,
                                    'vcpus': flavor.vcpus + 1,
                                    'disk': flavor.disk,
                                    'ram': flavor.ram,
                                    'swap': flavor.swap,
                                    'OS-FLV-EXT-DATA:ephemeral': eph,
                                    'extra_specs': extra_specs})

        # GET/init, set up expected behavior
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])

        # POST/init
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())
        api.nova.flavor_get_extras(IsA(http.HttpRequest),
                                   flavor.id, raw=True) \
                                   .AndReturn(extra_specs)
        api.nova.flavor_delete(IsA(http.HttpRequest), flavor.id)
        api.nova.flavor_create(IsA(http.HttpRequest),
                               new_flavor.name,
                               new_flavor.ram,
                               new_flavor.vcpus,
                               new_flavor.disk,
                               swap=new_flavor.swap,
                               ephemeral=eph,
                               flavorid=flavor.id,
                               is_public=True).AndReturn(new_flavor)
        api.nova.flavor_extra_set(IsA(http.HttpRequest),
                                  new_flavor.id, extra_specs)

        self.mox.ReplayAll()

        #run get test
        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        #run post test
        workflow_data = {'flavor_id': flavor.id,
                         'name': new_flavor.name,
                         'vcpus': new_flavor.vcpus,
                         'memory_mb': new_flavor.ram,
                         'disk_gb': new_flavor.disk,
                         'swap_mb': new_flavor.swap,
                         'eph_gb': eph,
                         'is_public': True}
        resp = self.client.post(url, workflow_data)
        self.assertNoFormErrors(resp)
        self.assertMessageCount(success=1)
        self.assertRedirectsNoFollow(resp, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_get_extras',
                                   'flavor_list',
                                   'flavor_delete',
                                   'flavor_create')})
    def test_update_flavor_update_flavor_error(self):
        # The first element has no extra specs
        flavor = self.flavors.first()
        projects = self.tenants.list()
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        extra_specs = getattr(flavor, 'extra_specs')
        new_flavor = flavors.Flavor(flavors.FlavorManager(None),
                                    {'id':
                                     "cccccccc-cccc-cccc-cccc-cccccccccccc",
                                     'name': flavor.name,
                                     'vcpus': flavor.vcpus + 1,
                                     'disk': flavor.disk,
                                     'ram': flavor.ram,
                                     'swap': 0,
                                     'OS-FLV-EXT-DATA:ephemeral': eph,
                                     'extra_specs': extra_specs})

        # GET/init, set up expected behavior
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])

        # POST
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
            .AndReturn(self.flavors.list())

        # POST/init
        api.nova.flavor_get_extras(IsA(http.HttpRequest),
                                   flavor.id, raw=True) \
                                   .AndReturn(extra_specs)
        api.nova.flavor_delete(IsA(http.HttpRequest), flavor.id)
        api.nova.flavor_create(IsA(http.HttpRequest),
                               new_flavor.name,
                               new_flavor.ram,
                               new_flavor.vcpus,
                               new_flavor.disk,
                               swap=new_flavor.swap,
                               ephemeral=eph,
                               flavorid=flavor.id,
                               is_public=True)\
                               .AndRaise(self.exceptions.nova)

        # Put mocks in replay mode
        self.mox.ReplayAll()

        # run get test
        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        # run post test
        workflow_data = {'flavor_id': flavor.id,
                         'name': new_flavor.name,
                         'vcpus': new_flavor.vcpus,
                         'memory_mb': new_flavor.ram,
                         'disk_gb': new_flavor.disk,
                         'swap_mb': new_flavor.swap,
                         'eph_gb': eph,
                         'is_public': True}
        resp = self.client.post(url, workflow_data)
        self.assertNoFormErrors(resp)
        self.assertMessageCount(error=1)
        self.assertRedirectsNoFollow(resp, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_get_extras',
                                   'flavor_list',
                                   'flavor_delete',
                                   'flavor_create',
                                   'flavor_access_list',
                                   'remove_tenant_from_flavor',
                                   'add_tenant_to_flavor')})
    def test_update_flavor_update_projects_error(self):
        # The first element has no extra specs
        flavor = self.flavors.first()
        projects = self.tenants.list()
        flavor_projects = [self.tenants.first()]
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        extra_specs = getattr(flavor, 'extra_specs')
        new_flavor = flavors.Flavor(flavors.FlavorManager(None),
                                    {'id':
                                     "cccccccc-cccc-cccc-cccc-cccccccccccc",
                                     'name': flavor.name,
                                     'vcpus': flavor.vcpus + 1,
                                     'disk': flavor.disk,
                                     'ram': flavor.ram,
                                     'swap': 0,
                                     'OS-FLV-EXT-DATA:ephemeral': eph,
                                     'os-flavor-access:is_public': False,
                                     'extra_specs': extra_specs})

        # GET/init, set up expected behavior
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])

        # POST/init
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())
        api.nova.flavor_get_extras(IsA(http.HttpRequest),
                                   flavor.id, raw=True) \
                                   .AndReturn(extra_specs)

        api.nova.flavor_delete(IsA(http.HttpRequest), flavor.id)
        api.nova.flavor_create(IsA(http.HttpRequest),
                               new_flavor.name,
                               new_flavor.ram,
                               new_flavor.vcpus,
                               new_flavor.disk,
                               swap=new_flavor.swap,
                               ephemeral=eph,
                               flavorid=flavor.id,
                               is_public=new_flavor.is_public) \
                               .AndReturn(new_flavor)

        new_flavor_projects = flavor_projects
        for project in new_flavor_projects:
            expect = api.nova.add_tenant_to_flavor(IsA(http.HttpRequest),
                                                   new_flavor.id, project.id)
            if project == projects[0]:
                expect.AndRaise(self.exceptions.nova)

        # Put mocks in replay mode
        self.mox.ReplayAll()

        # run get test
        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        # run post test
        data = self._get_workflow_data(new_flavor, access=flavor_projects)
        data['flavor_id'] = flavor.id
        resp = self.client.post(url, data)
        self.assertNoFormErrors(resp)
        self.assertMessageCount(error=1, warning=0)
        self.assertRedirectsNoFollow(resp, INDEX_URL)

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_list',)})
    def test_update_flavor_set_invalid_name(self):
        flavor = self.flavors.first()
        projects = self.tenants.list()
        eph = getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral')
        invalid_flavor_name = "m1.tiny()"

        # init
        api.nova.flavor_get(IsA(http.HttpRequest), flavor.id) \
                .MultipleTimes().AndReturn(flavor)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())

        self.mox.ReplayAll()

        # run get test
        url = reverse('horizon:admin:flavors:update', args=[flavor.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        # run post test
        workflow_data = {'flavor_id': flavor.id,
                         'name': invalid_flavor_name,
                         'vcpus': flavor.vcpus + 1,
                         'memory_mb': flavor.ram,
                         'disk_gb': flavor.disk,
                         'swap_mb': flavor.swap,
                         'eph_gb': eph,
                         'is_public': True}
        resp = self.client.post(url, workflow_data)
        self.assertFormErrors(resp, 1, 'Name may only contain letters, '
                              'numbers, underscores, periods and hyphens.')

    @test.create_stubs({api.keystone: ('tenant_list',),
                        api.nova: ('flavor_get',
                                   'flavor_list',)})
    def test_update_flavor_set_existing_name(self):
        flavor_a = self.flavors.list()[0]
        flavor_b = self.flavors.list()[1]
        projects = self.tenants.list()
        eph = getattr(flavor_a, 'OS-FLV-EXT-DATA:ephemeral')
        extra_specs = getattr(flavor_a, 'extra_specs')
        new_flavor = flavors.Flavor(flavors.FlavorManager(None),
                                    {'id': flavor_a.id,
                                    'name': flavor_b.name,
                                    'vcpus': flavor_a.vcpus,
                                    'disk': flavor_a.disk,
                                    'ram': flavor_a.ram,
                                    'swap': flavor_a.swap,
                                    'OS-FLV-EXT-DATA:ephemeral': eph,
                                    'extra_specs': extra_specs})

        # GET
        api.nova.flavor_get(IsA(http.HttpRequest), flavor_a.id) \
                .MultipleTimes().AndReturn(flavor_a)
        api.keystone.tenant_list(IsA(http.HttpRequest)) \
                .MultipleTimes().AndReturn([projects, False])

        # POST
        api.nova.flavor_list(IsA(http.HttpRequest), None) \
                .AndReturn(self.flavors.list())
        self.mox.ReplayAll()

        # get test
        url = reverse('horizon:admin:flavors:update', args=[flavor_a.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/flavors/update.html")

        # post test
        data = {'flavor_id': new_flavor.id,
                'name': new_flavor.name,
                'vcpus': new_flavor.vcpus,
                'memory_mb': new_flavor.ram,
                'disk_gb': new_flavor.disk,
                'swap_mb': new_flavor.swap,
                'eph_gb': eph,
                'is_public': True}
        resp = self.client.post(url, data)
        self.assertFormErrors(resp, 1, 'The name &quot;m1.massive&quot; '
                              'is already used by another flavor.')
