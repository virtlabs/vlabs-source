from kubernetes import config as kconf, client
from kubernetes.client import V1PersistentVolumeClaimVolumeSource, V1GlusterfsVolumeSource, V1VolumeMount
from kubernetes.client.models.v1_object_meta import V1ObjectMeta
from kubernetes.client.models.v1_volume import V1Volume
import openshift.client.models
import kubernetes.client.models
import openshift.client
from openshift import config as oconf
from kubernetes.client.rest import ApiException
import os, yaml


class Provision:
    def __init__(self, user):
        cfg = '/root/.kube/' + user + '.config'
        kcfg = kconf.new_client_from_config(cfg)
        ocfg = oconf.new_client_from_config(cfg)
        self.o1 = openshift.client.OapiApi(ocfg)
        self.k1 = kubernetes.client.CoreV1Api(kcfg)
        path = os.path.dirname(__file__)
        stream = file((os.path.join(path, '../marketplace/vlabs_template.yml')), 'r')
        ysrvc = yaml.load(stream)
        if str(ysrvc['svcsdomain']).startswith('$'):
            self.domain = os.getenv('SVCSDOMAIN')
        else:
            self.domain = ysrvc['svcsdomain']

    def createsvc(self, deploy, port, imagename, namespace, envvar, nameapp, service, pvc, volumename, datadir):
        bservice = client.V1Service()
        smeta = V1ObjectMeta()
        dcmeta = V1ObjectMeta()
        pmt = V1ObjectMeta()
        sspec = client.V1ServiceSpec()
        bdc = openshift.client.V1DeploymentConfig()
        dcspec = openshift.client.V1DeploymentConfigSpec()
        strategy = openshift.client.V1DeploymentStrategy()
        rollingparams = openshift.client.V1RollingDeploymentStrategyParams()
        podtemp = client.V1PodTemplateSpec()
        podspec = client.V1PodSpec()
        container = client.V1Container()

        idname = nameapp + "-" + deploy

        smeta.name = idname   # !!!
        smeta.namespace = namespace
        smeta.labels = {"label": idname, "bundle": service + "-" + nameapp}

        sspec.selector = {"label": idname}
        sspec.ports = []

        for l in range(0, len(port)):
            p = client.V1ServicePort()
            p.name = "{port}-{tcp}".format(**port[l])
            p.protocol = "TCP"
            p.port = port[l]['tcp']
            p.target_port = "{port}-{tcp}".format(**port[l])
            sspec.ports.append(p)
            if port[l]['route'] == 'yes':
                self.createroute(p.target_port, idname, namespace, service, nameapp, l)


        bservice.api_version = 'v1'
        bservice.kind = 'Service'
        bservice.metadata = smeta
        bservice.spec = sspec
        bservice.api_version = 'v1'

        # DeploymentConfig

        dcmeta.labels = {"label": idname, "bundle": service + "-" + nameapp}
        dcmeta.name = idname
        dcmeta.namespace = namespace

        rollingparams.interval_seconds = 1

        strategy.labels = {"label": idname, "bundle": service + "-" + nameapp}
        strategy.type = 'Rolling'
        strategy.rolling_params = rollingparams

        container.image = imagename
        container.name = idname
        container.env = []
        if pvc:
            vm = V1VolumeMount()
            vm.mount_path = datadir
            vm.name = volumename
            container.volume_mounts = [vm]
        else:
            pass

        for key in envvar:
            v = client.V1EnvVar()
            v.name = key
            v.value = envvar[key]
            container.env.append(v)

        container.ports = []
        for o in range(0, len(port)):
            p = client.V1ContainerPort()
            p.name = ("{port}-{tcp}".format(**port[o]))
            p.protocol = "TCP"
            p.container_port = port[o]['tcp']
            container.ports.append(p)

        pmt.labels = {"label": idname, "bundle": service + "-" + nameapp}
        pmt.name = idname

        podspec.containers = [container]
        if pvc:
            vol = V1Volume()
            pvcname = V1PersistentVolumeClaimVolumeSource()
            volgfs = V1GlusterfsVolumeSource()

            pvcname.claim_name = volumename

            volgfs.endpoints = volumename
            volgfs.path = datadir

            #vol.glusterfs = volgfs
            vol.name = volumename
            vol.persistent_volume_claim = pvcname
            podspec.volumes = [vol]
        else:
            pass

        podtemp.metadata = pmt
        podtemp.spec = podspec

        dcspec.replicas = 1
        dcspec.selector = {"label": idname}
        dcspec.template = podtemp
        dcspec.strategy = strategy

        bdc.api_version = 'v1'
        bdc.spec = dcspec
        bdc.metadata = dcmeta
        bdc.kind = 'DeploymentConfig'

        try:
            self.k1.create_namespaced_service(namespace=namespace, body=bservice, pretty='true')
        except ApiException as e:
            print("Exception when calling OapiApi->create_service: %s\n" % e)

        try:
            self.o1.create_namespaced_deployment_config(namespace=namespace, body=bdc, pretty='true')
        except ApiException as e:
            print("Exception when calling OapiApi->create_dc: %s\n" % e)

    def createroute(self, target, idname, namespace, service, nameapp, l):
        rbody = openshift.client.V1Route()
        routemeta = V1ObjectMeta()
        routespec = openshift.client.V1RouteSpec()
        routeport = openshift.client.V1RoutePort()
        routeto = openshift.client.V1RouteTargetReference()
        secureroute = openshift.client.V1TLSConfig()

        routeport.target_port = target
        routeto.kind = 'Service'
        routeto.name = idname
        routeto.weight = 100

        secureroute.termination = 'Edge'
        secureroute.insecure_edge_termination_policy = 'Redirect'

        routespec.host = idname + '-' + str(l) + str(self.domain) ##'.web.roma2.infn.it'
        routespec.port = routeport
        routespec.to = routeto
        routespec.tls = secureroute

        routemeta.labels = {"label": idname, "bundle": service + "-" + nameapp}
        routemeta.name = idname + '-' + str(l)
        routemeta.namespace = namespace

        rbody.api_version = 'v1'
        rbody.kind = 'Route'
        rbody.metadata = routemeta
        rbody.spec = routespec

        try:
            self.o1.create_namespaced_route(namespace=namespace, body=rbody, pretty='true')

        except ApiException as e:
            print("Exception when calling OapiApi->create_route: %s\n" % e)
