from jina.hubble.helper import parse_hub_uri
from jina.hubble.hubio import HubIO

IS_LOCAL = False

if IS_LOCAL:
    gateway_image = 'custom-jina'
else:
    gateway_image = 'gcr.io/jina-showcase/custom-jina:latest'


def to_dns_name(name):
    return name.replace('/', '-').replace('_', '-').lower()


def deploy_service(
    name,
    namespace,
    port_in,
    port_out,
    port_ctrl,
    port_expose,
    image_name,
    container_cmd,
    container_args,
    logger,
    replicas,
    pull_policy,
    init_container=None,
):
    from jina.peapods.pods.kubernetes import kubernetes_tools

    # small hack - we can always assume the ports are the same for all executors since they run on different k8s pods
    port_expose = 8080
    port_in = 8081
    port_out = 8082
    port_ctrl = 8083

    logger.info(
        f'🔋\tCreate Service for "{name}" with image "{name}" pulling from "{image_name}" \ncontainer_cmd: {container_cmd}\n{name} container_args: {container_args}'
    )
    kubernetes_tools.create(
        'service',
        {
            'name': name,
            'target': name,
            'namespace': namespace,
            'port_expose': port_expose,
            'port_in': port_in,
            'port_out': port_out,
            'port_ctrl': port_ctrl,
            'type': 'ClusterIP',
        },
    )

    logger.info(
        f'🐳\tCreate Deployment for "{image_name}" with replicas {replicas} and init_container {init_container is not None}'
    )

    if init_container:
        kubernetes_tools.create(
            'deployment-init',
            {
                'name': name,
                'namespace': namespace,
                'image': image_name,
                'replicas': replicas,
                'command': container_cmd,
                'args': container_args,
                'port_expose': port_expose,
                'port_in': port_in,
                'port_out': port_out,
                'port_ctrl': port_ctrl,
                'pull_policy': pull_policy,
                **init_container,
            },
        )
    else:
        kubernetes_tools.create(
            'deployment',
            {
                'name': name,
                'namespace': namespace,
                'image': image_name,
                'replicas': replicas,
                'command': container_cmd,
                'args': container_args,
                'port_expose': port_expose,
                'port_in': port_in,
                'port_out': port_out,
                'port_ctrl': port_ctrl,
                'pull_policy': pull_policy,
            },
        )
    return f'{name}.{namespace}.svc.cluster.local'


# def deploy_glue_executor(glue_executor, namespace, logger):
#     if glue_executor.uses == 'gcr.io/jina-showcase/match-merger':
#         return deploy_service(
#             to_dns_name(glue_executor.name),
#             namespace,
#             glue_executor.port_in,
#             glue_executor.port_out,
#             glue_executor.port_ctrl,
#             glue_executor.port_expose,
#             glue_executor.uses,
#             '["jina"]',
#             f'["executor", "--uses", "config.yml", {get_cli_params(glue_executor, skip_list=["uses_with"])}]',
#             logger,
#         )
#     else:
#         return deploy_service(
#             to_dns_name(glue_executor.name),
#             namespace,
#             glue_executor.port_in,
#             glue_executor.port_out,
#             glue_executor.port_ctrl,
#             glue_executor.port_expose,
#             'gcr.io/jina-showcase/custom-jina:latest',
#             '["jina"]',
#             f'["executor", "--uses", "{glue_executor.uses}", {get_cli_params(glue_executor, skip_list=["uses_with"])}]',
#             logger,
#         )


def get_cli_params(arguments, skip_list=()):
    arguments.host = '0.0.0.0'
    skip_attributes = [
        'uses',  # set manually
        'uses_with',  # set manually
        'runtime_cls',  # set manually
        'workspace',
        'log_config',
        'dynamic_routing',
        'hosts_in_connect',
        'polling_type',
        'k8s_namespace',
        'uses_after',
        'uses_before',
        'replicas',
        'shards',
        'parallel',
        'polling',
        'port_in',
        'port_out',
        'port_ctrl',
        'port_expose',
        'k8s_init_container_command',
        'k8s_uses_init',
        'k8s_mount_path',
    ] + list(skip_list)
    arg_list = [
        [attribute, attribute.replace('_', '-'), value]
        for attribute, value in arguments.__dict__.items()
    ]
    cli_args = []
    for attribute, cli_attribute, value in arg_list:
        if attribute in skip_attributes:
            continue
        if type(value) == bool and value:
            cli_args.append(f'"--{cli_attribute}"')
        else:
            if value:
                value = str(value)
                value = value.replace('\'', '').replace('"', '\\"')
                cli_args.append(f'"--{cli_attribute}", "{value}"')

    cli_args.append('"--port-expose", "8080"')
    cli_args.append('"--port-in", "8081"')
    cli_args.append('"--port-out", "8082"')
    cli_args.append('"--port-ctrl", "8083"')

    cli_string = ', '.join(cli_args)
    return cli_string


def get_image_name(uses):
    try:
        scheme, name, tag, secret = parse_hub_uri(uses)
        meta_data = HubIO.fetch_meta(name)
        image_name = meta_data.image_name
        return image_name
    except Exception:
        return uses.replace('docker://', '')


def prepare_flow(flow):
    namespace = flow.args.name
    flow.args.host = f'gateway.{namespace}.svc.cluster.local'
    flow.host = f'gateway.{namespace}.svc.cluster.local'
    return flow.build(copy_flow=True)


def dictionary_to_cli_param(dictionary):
    return dictionary.__str__().replace("'", "\\\"") if dictionary else ""


def get_needs(flow, pod):
    needs = []
    for pod_name in pod.needs:
        needed_pod = flow._pod_nodes[pod_name]
        if pod_name != 'gateway' and needed_pod.args.parallel > 1:
            needs.append(pod_name + '_tail')
        else:
            needs.append(pod_name)


# def get_k8s_flow(flow):
#     k8s_flow = Flow(
#         name=flow.args.name,
#         port_expose=flow.port_expose,
#         protocol=flow.protocol,
#         grpc_data_requests=True,
#     )
#     pod_name_to_parallel = dict()
#     for pod_name, pod in flow._pod_nodes.items():
#         if pod_name == 'gateway':
#             continue
#         needs = get_needs(flow, pod)
#
#         if type(pod).__name__ == 'CompoundPod':
#             pod_args = pod.replicas_args[0]
#             pod_args.name = pod_args.name.split('/')[0]
#             replicas = len(pod.replicas_args)
#         else:
#             pod_args = pod.args
#             replicas = 1
#         pod_name_to_parallel[pod_name] = (pod.args.parallel, replicas)
#         if pod_args.parallel > 1:
#             k8s_flow = k8s_flow.add(
#                 name=pod_args.name + '_head',
#                 uses=pod_args.uses_before,
#                 port_in=8081,
#                 host=f'{to_dns_name(pod_name)}-head.{k8s_flow.args.name}.svc.cluster.local',
#                 external=True,
#                 needs=needs,
#             )
#             for i in range(pod_args.parallel):
#                 k8s_flow = k8s_flow.add(
#                     name=pod_args.name + f'_{i}',
#                     uses=pod_args.uses,
#                     port_in=8081,
#                     host=f'{to_dns_name(pod_name)}-{i}.{k8s_flow.args.name}.svc.cluster.local',
#                     uses_with=pod_args.uses_with,
#                     k8s_uses_init=pod_args.k8s_uses_init,
#                     k8s_uses_with_init=pod_args.k8s_uses_with_init,
#                     pea_id=i,
#                     external=True,
#                     needs=[pod_args.name + '_head'],
#                 )
#             k8s_flow = k8s_flow.add(
#                 name=pod_args.name + '_tail',
#                 uses=pod_args.uses_after,
#                 port_in=8081,
#                 host=f'{to_dns_name(pod_name)}-tail.{k8s_flow.args.name}.svc.cluster.local',
#                 uses_with=pod_args.uses_with,
#                 external=True,
#                 needs=[pod_args.name + f'_{i}' for i in range(pod_args.parallel)],
#             )
#         else:
#             k8s_flow = k8s_flow.add(
#                 name=pod_args.name,
#                 uses=pod_args.uses,
#                 port_in=8081,
#                 host=f'{to_dns_name(pod_name)}.{k8s_flow.args.name}.svc.cluster.local',
#                 uses_with=pod_args.uses_with,
#                 external=True,
#                 needs=needs,
#             )
#     return prepare_flow(k8s_flow), pod_name_to_parallel
#


def convert_to_table_name(pod_name):
    return pod_name.replace('-', '_')


def get_init_container_args(pod):
    # if (pod.args.uses == 'jinahub+docker://AnnoySearcher' or
    #         pod.args.uses == 'jinahub+docker://FaissSearcher' or
    #         pod.args.uses == 'gcr.io/mystical-sweep-320315/annoy-with-grpc'):
    #     init_image_name = get_image_name(
    #         'jinahub+docker://PostgreSQLStorage'
    #     )
    #     postgres_cluster_ip = f'postgres.postgres.svc.cluster.local'
    #
    #     pod_name = pod.name.rsplit("_", 1)[0]
    #     table_name = convert_to_table_name(pod_name)
    #     shards = pod_name_to_parallel[pod_name][0]
    # python_script = (
    #     'import os; '
    #     'os.chdir(\'/\'); '
    #     'from workspace import PostgreSQLStorage; '
    #     'storage = PostgreSQLStorage('
    #     f'hostname="{postgres_cluster_ip}",'
    #     'port=5432,'
    #     'username="postgresadmin",'
    #     'database="postgresdb",'
    #     f'table="{convert_to_table_name(pod_name)}",'
    #     '); '
    #     'storage.dump(parameters={'
    #     '"dump_path": "/shared", '
    #     f'"shards": {pod_name_to_parallel[pod_name][0]}'
    #     '});'
    # ).replace("\"", "\\\"")

    if pod.args.k8s_uses_init:
        init_container = {
            'init-name': 'init',
            'init-image': pod.args.k8s_uses_init,
            'mount-path': pod.args.k8s_mount_path,
            'init-command': f'{pod.args.k8s_container_init_command}',
        }
    else:
        init_container = None
    return init_container


# def create_in_k8s(k8s_flow, pod_name_to_parallel):
#     namespace = k8s_flow.args.name
#     for pod_name, pod in k8s_flow._pod_nodes.items():
#         if pod_name == 'gateway':
#             continue
#         image_name = get_image_name(pod.args.uses)
#         pea_arg = pod.peas_args['peas'][0]
#         pea_name = pea_arg.name
#         pea_dns_name = to_dns_name(pea_name)
#         init_container_args = get_init_container_args(pod)
#         uses_metas = dictionary_to_cli_param({'pea_id': pea_arg.pea_id})
#         uses_with = dictionary_to_cli_param(pea_arg.uses_with)
#         uses_with_string = f'"--uses-with", "{uses_with}", ' if uses_with else ''
#         if image_name == 'BaseExecutor':
#             image_name = 'jinaai/jina'
#             container_args = (
#                 f'["executor", '
#                 f'"--uses", "BaseExecutor", '
#                 f'"--uses-metas", "{uses_metas}", '
#                 + uses_with_string
#                 + f'{get_cli_params(pea_arg)}]'
#             )
#
#         else:
#             container_args = (
#                 f'["executor", '
#                 f'"--uses", "config.yml", '
#                 f'"--uses-metas", "{uses_metas}", '
#                 + uses_with_string
#                 + f'{get_cli_params(pea_arg)}]'
#             )
#
#         if pod_name.endswith('_tail') or pod_name.endswith('_head'):
#             replicas = 1
#         else:
#             replicas = pod_name_to_parallel[pod_name.rsplit("_", 1)[0]][1]
#
#         deploy_service(
#             pea_dns_name,
#             namespace=namespace,
#             port_in=pea_arg.port_in,
#             port_out=pea_arg.port_out,
#             port_ctrl=pea_arg.port_ctrl,
#             port_expose=pea_arg.port_expose,
#             image_name=image_name,
#             container_cmd='["jina"]',
#             container_args=container_args,
#             logger=k8s_flow.logger,
#             replicas=replicas,
#             init_container=init_container_args,
#         )
#
#     gateway_args = k8s_flow._pod_nodes['gateway'].peas_args['peas'][0]
#     deploy_service(
#         gateway_args.name,
#         namespace,
#         gateway_args.port_in,
#         gateway_args.port_out,
#         gateway_args.port_ctrl,
#         gateway_args.port_expose,
#         'gcr.io/jina-showcase/custom-jina:latest',
#         container_cmd='["jina"]',
#         container_args=f'["gateway", ' f'{get_cli_params(gateway_args)}]',
#         logger=k8s_flow.logger,
#         replicas=1,
#         init_container=None,
#     )


# def deploy(flow):
#     """Deploys the Flow. Currently only Kubernetes is supported.
#     Each pod is deployed in a stateful set and we use zmq level communication.
#     """
#     from jina.peapods.pods.kubernetes import kubernetes_tools
#
#     # TODO needed?
#     flow = prepare_flow(flow)
#
#     flow.logger.info(f'✨ Deploy Flow on Kubernetes...')
#     namespace = flow.args.name
#     flow.logger.info(f'📦\tCreate Namespace {namespace}')
#     kubernetes_tools.create('namespace', {'name': namespace})
#
#     k8s_flow, pod_name_to_parallel = get_k8s_flow(flow)
#
#     create_in_k8s(k8s_flow, pod_name_to_parallel)
#
#     # flow.logger.info(f'🌐\tCreate "Ingress resource"')
#     # kubernetes_tools.create_gateway_ingress(namespace)
