import os
from .k8sclient import kubeclient
from .models import DeploymentModel
from typing import Dict, List, Optional
from collections import Counter
from itertools import combinations
from kubernetes.client import V1PodDisruptionBudget

NUMBER_OF_NODES_UPGRADE = int(os.getenv('NUMBER_OF_NODES_UPGRADE', '2'))

k8s_client = kubeclient()

namespace_checks_report: Dict[str,Dict] = {}
topology_spread_checks_report: Dict[str,Dict] = {}


ZONE_TOPOLOGY_KEY = 'topology.kubernetes.io/zone'
HOSTNAME_TOPOLOGY_KEY = 'kubernetes.io/hostname'
DEFAULT_TOPOLOGY_SKEW = 1

def set_topology_spec_report(name:str,namespace:str,replicas:int,zone_violated:bool,hostname_violated:bool,node_info:List[Dict[str,str]]=None,voilated:bool=False,comments:Optional[str]=None) -> Dict[str,object]:
    return {
        'Deployment_name': name,
        'Namespace': namespace,
        'Replicas': replicas,
        'Zone_violated': zone_violated,
        'Hostname_violated': hostname_violated,
        'Node_info': node_info if node_info else 'not applicable',
        'Voilated?': voilated,
        'Comments': comments if comments else 'not applicable'
    }

def set_upgrade_spec_report(name:str,namespace:str,replicas:int,allowed_disruptions:Optional[int],blocking_pdb:str,node_info:List[Dict[str,str]]=None,comments:Optional[str]=None,blocking_possible:Optional[str]=None) -> Dict[str,object]:
    return {
        'Deployment_name': name,
        'Namespace': namespace,
        'Replicas': replicas,
        'Allowed_disruptions': allowed_disruptions if allowed_disruptions is not None else 'not applicable',
        'Blocking_PDB': blocking_pdb,
        'Node_info': node_info if node_info else 'not applicable',
        'Comments': comments if comments else 'not applicable',
        'Blocking_possible?': blocking_possible if blocking_possible else 'not applicable',
    }


def get_node_zone(core_api,node_name:str) -> str:
    node = core_api.read_node(node_name)
    labels = node.metadata.labels or {}
    return labels.get('topology.kubernetes.io/zone') or labels.get('failure-domain.beta.kubernetes.io/zone') or 'unknown'


def get_deployment_pods_node_info(namespace:str,deployment: DeploymentModel) -> Dict[str,object]:
    core_api = k8s_client.coreV1Api()
    match_labels = deployment.spec.selector.get('matchLabels', {})
    label_selector = ','.join(f'{key}={value}' for key, value in match_labels.items())

    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

    pod_node_names = [pod.spec.node_name for pod in pods.items if pod.spec.node_name]
    node_names = set(pod_node_names)
    zone_by_node = {node_name: get_node_zone(core_api,node_name) for node_name in node_names}
    pods_per_node = dict(Counter(pod_node_names))

    node_info = [
        {'node': pod.spec.node_name, 'zone': zone_by_node[pod.spec.node_name]}
        for pod in pods.items if pod.spec.node_name
    ]

    return {'node_info': node_info, 'pod_count': len(pods.items), 'pods_per_node': pods_per_node}


def get_deployment_node_summary(namespace:str,deployment: DeploymentModel) -> Dict[str,Dict[str,object]]:
    pod_node_data = get_deployment_pods_node_info(namespace,deployment)
    pods_per_node = pod_node_data['pods_per_node']
    zone_by_node = {entry['node']: entry['zone'] for entry in pod_node_data['node_info']}

    return {
        node_name: {'zone': zone_by_node.get(node_name, 'unknown'), 'replica_count': replica_count}
        for node_name, replica_count in pods_per_node.items()
    }
    

def check_pod_antiaffinity(namespace:str,deployment: DeploymentModel) -> bool:
    pod_spec = deployment.spec.template.spec
    affinity = pod_spec.affinity

    if not affinity or not affinity.podAntiAffinity:
        return False

    pod_antiaffinity = affinity.podAntiAffinity
    return bool(
        pod_antiaffinity.requiredDuringSchedulingIgnoredDuringExecution
        or pod_antiaffinity.preferredDuringSchedulingIgnoredDuringExecution
    )





def get_replica_distribution(node_summary:Dict[str,Dict[str,object]],topology_key:str) -> Dict[str,int]:
    distribution: Dict[str,int] = {}
    for node_name, info in node_summary.items():
        domain = node_name if topology_key == HOSTNAME_TOPOLOGY_KEY else info['zone']
        distribution[domain] = distribution.get(domain, 0) + info['replica_count']
    return distribution


def is_topology_key_violated(node_summary:Dict[str,Dict[str,object]],topology_key:str,max_skew:int) -> bool:
    distribution = get_replica_distribution(node_summary,topology_key)
    if not distribution:
        return False
    return max(distribution.values()) - min(distribution.values()) > max_skew


def get_topology_key_skew(deployment: DeploymentModel,topology_key:str) -> int:
    constraints = deployment.spec.template.spec.topologySpreadConstraints
    for constraint in constraints:
        if constraint.topologyKey == topology_key:
            return constraint.maxSkew

    affinity = deployment.spec.template.spec.affinity
    pod_antiaffinity = affinity.podAntiAffinity if affinity else None
    if pod_antiaffinity:
        required_keys = {term.topologyKey for term in pod_antiaffinity.requiredDuringSchedulingIgnoredDuringExecution}
        if topology_key in required_keys:
            return 0

        preferred_keys = {term.podAffinityTerm.topologyKey for term in pod_antiaffinity.preferredDuringSchedulingIgnoredDuringExecution}
        if topology_key in preferred_keys:
            return DEFAULT_TOPOLOGY_SKEW

    return DEFAULT_TOPOLOGY_SKEW


def check_topology_spread(namespace:str,deployment: DeploymentModel) -> Dict[str,Dict]:
    replicas = deployment.spec.replicas or 0

    if replicas <= 1:
        topology_spread_checks_report[namespace] = set_topology_spec_report(
            deployment.metadata['name'],namespace,replicas,
            False,False,None,False,
            'replicas are less than or equal to 1, skipping topology spread checks'
        )
        return topology_spread_checks_report

    node_summary = get_deployment_node_summary(namespace,deployment)
    node_info = get_deployment_pods_node_info(namespace,deployment)['node_info']

    zone_violated = is_topology_key_violated(node_summary,ZONE_TOPOLOGY_KEY,get_topology_key_skew(deployment,ZONE_TOPOLOGY_KEY))
    hostname_violated = is_topology_key_violated(node_summary,HOSTNAME_TOPOLOGY_KEY,get_topology_key_skew(deployment,HOSTNAME_TOPOLOGY_KEY))
    violated = zone_violated and hostname_violated

    topology_spread_checks_report[namespace] = set_topology_spec_report(
        deployment.metadata['name'],namespace,replicas,
        zone_violated,hostname_violated,node_info,violated,
        'pods are unevenly spread across both nodes and zones' if violated else 'pods are adequately spread across nodes and/or zones'
    )
    return topology_spread_checks_report


def find_matching_pdb(namespace:str,deployment: DeploymentModel) -> Optional[V1PodDisruptionBudget]:
    policy_api = k8s_client.policyV1Api()
    pod_labels = deployment.spec.template.metadata.get('labels', {})

    pdbs = policy_api.list_namespaced_pod_disruption_budget(namespace=namespace)

    for pdb in pdbs.items:
        pdb_selector = pdb.spec.selector.match_labels if pdb.spec.selector and pdb.spec.selector.match_labels else {}
        if pdb_selector and pdb_selector.items() <= pod_labels.items():
            return pdb

    return None


def check_pdb_exists(namespace:str,deployment: DeploymentModel) -> bool:
    return find_matching_pdb(namespace,deployment) is not None


def get_pdb_allowed_disruptions(namespace:str,deployment: DeploymentModel) -> Optional[int]:
    pdb = find_matching_pdb(namespace,deployment)
    return pdb.status.disruptions_allowed if pdb and pdb.status else None


def node_upgrade_precheck(namespace:str,deployment: DeploymentModel) -> Dict[str,Dict]:
    replicas = deployment.spec.replicas or 0
    allowed_disruptions = get_pdb_allowed_disruptions(namespace,deployment)

    if replicas < 1:
        namespace_checks_report[namespace] = set_upgrade_spec_report(deployment.metadata['name'],namespace,replicas,allowed_disruptions,'not applicable',None,"not applicable, replicas are less than 1","No")
        return namespace_checks_report

    if allowed_disruptions is None:
        node_info = get_deployment_pods_node_info(namespace,deployment)['node_info']
        namespace_checks_report[namespace] = set_upgrade_spec_report(deployment.metadata['name'],namespace,replicas,allowed_disruptions,'none',node_info,"This pod will be disrupted during upgrade because of lack of PDB and replicas are greater than or equal to 1","No")
        return namespace_checks_report

    if allowed_disruptions == 0:
        pdb_info = find_matching_pdb(namespace,deployment)
        node_info = get_deployment_pods_node_info(namespace,deployment)['node_info']
        namespace_checks_report[namespace] = set_upgrade_spec_report(deployment.metadata['name'],namespace,replicas,allowed_disruptions,pdb_info.metadata.name,node_info,"The nodes where the pods are running might block the upgrade because of PDB violations","Yes")
        return namespace_checks_report

    # allowed_disruptions > 0: check whether draining up to NUMBER_OF_NODES_UPGRADE nodes
    # at once would evict more of this deployment's pods than the PDB currently allows
    node_summary = get_deployment_node_summary(namespace,deployment)
    node_info = get_deployment_pods_node_info(namespace,deployment)['node_info']
    nodes = list(node_summary.keys())
    pdb_info = find_matching_pdb(namespace,deployment)

    for node_upgrade_num in range(1,NUMBER_OF_NODES_UPGRADE+1):
        for combo in combinations(nodes, node_upgrade_num):
            total_pods_on_nodes = sum(node_summary[node]['replica_count'] for node in combo)
            if total_pods_on_nodes > allowed_disruptions:
                namespace_checks_report[namespace] = set_upgrade_spec_report(deployment.metadata['name'],namespace,replicas,allowed_disruptions,pdb_info.metadata.name,node_info,"The nodes where the pods are running might block the upgrade because of PDB violations","Yes")
                return namespace_checks_report

    namespace_checks_report[namespace] = set_upgrade_spec_report(deployment.metadata['name'],namespace,replicas,allowed_disruptions,pdb_info.metadata.name,node_info,"The nodes where the pods are running will not block the upgrade","No")

    return namespace_checks_report