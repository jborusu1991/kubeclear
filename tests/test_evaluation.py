from kubeclear import evaluation
from kubeclear.models import DeploymentModel
from kubernetes import client 

def define_deployment_model(name: str, replicas: int) -> DeploymentModel:
    return DeploymentModel(
        apiVersion="apps/v1",
        kind="Deployment",
        metadata={"name": name},
        spec={
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [
                        {
                            "name": f"{name}-container",
                            "image": "nginx:latest",
                            "ports": [{"containerPort": 80}],
                        }
                    ]
                },
            },
        },
    )


def pdb_create(name: str, min_available: int) -> client.V1PodDisruptionBudget:
    return client.V1PodDisruptionBudget(
    api_version="policy/v1",
    kind="PodDisruptionBudget",
    metadata=client.V1ObjectMeta(name=name),
    spec=client.V1PodDisruptionBudgetSpec(
        min_available=min_available,
        selector=client.V1LabelSelector(match_labels={"app": "my-app"})
    )
)



def test_node_upgrade_precheck_replicas_less_than_one(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 0)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return None
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)

    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 0
    assert report['test-namespace']['Allowed_disruptions'] == 'not applicable'
    assert report['test-namespace']['Blocking_PDB'] =='not applicable'
    assert report['test-namespace']['Node_info'] == 'not applicable'
    assert report['test-namespace']['Blocking_possible?'] == 'No'
    assert report['test-namespace']['Comments'] == 'not applicable, replicas are less than 1'


def test_node_upgrade_precheck_replicas_greater_than_one_pdb_none(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 3)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return None
    def mock_get_deployment_pods_node_info(ns, dep):
        node_info = [{'node':'node-1', 'zone': 'us-east-1a'}]
        return  {'node_info': node_info, 'pod_count': 2, 'pods_per_node': 2}
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)
    monkeypatch.setattr(evaluation, "get_deployment_pods_node_info", mock_get_deployment_pods_node_info)

    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 3
    assert report['test-namespace']['Allowed_disruptions'] == 'not applicable'
    assert report['test-namespace']['Blocking_PDB'] == 'none'
    assert report['test-namespace']['Node_info'] == [{'node': 'node-1', 'zone': 'us-east-1a'}]
    assert report['test-namespace']['Blocking_possible?'] == 'No'
    assert report['test-namespace']['Comments'] == 'This pod will be disrupted during upgrade because of lack of PDB and replicas are greater than or equal to 1'

def test_node_upgrade_precheck_replicas_greater_than_one_pdb_allows_disruption_zero(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 3)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return 0
    def mock_get_deployment_pods_node_info(ns, dep):
        node_info = [{'node':'node-1', 'zone': 'us-east-1a'}]
        return  {'node_info': node_info, 'pod_count': 2, 'pods_per_node': 2}
    def mock_find_matching_pdb(ns, dep):
        return pdb_create("test-pdb", 2)
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)
    monkeypatch.setattr(evaluation, "get_deployment_pods_node_info", mock_get_deployment_pods_node_info)
    monkeypatch.setattr(evaluation, "find_matching_pdb", mock_find_matching_pdb)

    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 3
    assert report['test-namespace']['Allowed_disruptions'] == 0
    assert report['test-namespace']['Blocking_PDB'] == 'test-pdb'
    assert report['test-namespace']['Node_info'] == [{'node': 'node-1', 'zone': 'us-east-1a'}]
    assert report['test-namespace']['Blocking_possible?'] == 'Yes'
    assert report['test-namespace']['Comments'] == 'The nodes where the pods are running might block the upgrade because of PDB violations'    

def test_node_upgrade_precheck_replicas_greater_than_one_pdb_allows_disruption_greater_than_zero(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 3)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return 1
    def mock_get_deployment_node_summary(ns, dep):
        return  {'node-1': {'zone': 'us-east-1a', 'replica_count': 3}}
    def mock_find_matching_pdb(ns, dep):
        return pdb_create("test-pdb", 2)
    def mock_get_deployment_pods_node_info(ns, dep):
        node_info = [{'node':'node-1', 'zone': 'us-east-1a'}]
        return  {'node_info': node_info, 'pod_count': 3, 'pods_per_node': 3}
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)
    monkeypatch.setattr(evaluation, "get_deployment_node_summary", mock_get_deployment_node_summary)
    monkeypatch.setattr(evaluation, "find_matching_pdb", mock_find_matching_pdb)
    monkeypatch.setattr(evaluation, "get_deployment_pods_node_info", mock_get_deployment_pods_node_info)
    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 3
    assert report['test-namespace']['Allowed_disruptions'] == 1
    assert report['test-namespace']['Blocking_PDB'] == 'test-pdb'
    assert report['test-namespace']['Node_info'] == [{'node': 'node-1', 'zone': 'us-east-1a'}]
    assert report['test-namespace']['Blocking_possible?'] == 'Yes'
    assert report['test-namespace']['Comments'] == 'The nodes where the pods are running might block the upgrade because of PDB violations'    


def test_node_upgrade_precheck_replicas_greater_than_one_pdb_allows_disruption_is_two(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 5)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return 2
    def mock_get_deployment_node_summary(ns, dep):
        return  {'node-1': {'zone': 'us-east-1a', 'replica_count': 3},'node-2': {'zone': 'us-east-1b', 'replica_count': 2}}
    def mock_find_matching_pdb(ns, dep):
        return pdb_create("test-pdb", 3)
    def mock_get_deployment_pods_node_info(ns, dep):
        node_info = [{'node':'node-1', 'zone': 'us-east-1a'}, {'node':'node-2', 'zone': 'us-east-1b'}]
        return  {'node_info': node_info, 'pod_count': 5, 'pods_per_node': 3}
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)
    monkeypatch.setattr(evaluation, "get_deployment_node_summary", mock_get_deployment_node_summary)
    monkeypatch.setattr(evaluation, "find_matching_pdb", mock_find_matching_pdb)
    monkeypatch.setattr(evaluation, "get_deployment_pods_node_info", mock_get_deployment_pods_node_info)
    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 5
    assert report['test-namespace']['Allowed_disruptions'] == 2
    assert report['test-namespace']['Blocking_PDB'] == 'test-pdb'
    assert report['test-namespace']['Node_info'] == [{'node': 'node-1', 'zone': 'us-east-1a'}, {'node': 'node-2', 'zone': 'us-east-1b'}]
    assert report['test-namespace']['Blocking_possible?'] == 'Yes'
    assert report['test-namespace']['Comments'] == 'The nodes where the pods are running might block the upgrade because of PDB violations'

def test_node_upgrade_precheck_replicas_greater_than_one_pdb_allows_disruption_is_two_noblock(monkeypatch):
    namespace = "test-namespace"
    deployment = define_deployment_model("test-deployment", 3)
    def mock_get_pdb_allowed_disruptions(ns, dep):
        return 2
    def mock_get_deployment_node_summary(ns, dep):
        return  {'node-1': {'zone': 'us-east-1a', 'replica_count': 1},'node-2': {'zone': 'us-east-1b', 'replica_count': 1},'node-3': {'zone': 'us-east-1c', 'replica_count': 1}}
    def mock_find_matching_pdb(ns, dep):
        return pdb_create("test-pdb", 1)
    def mock_get_deployment_pods_node_info(ns, dep):
        node_info = [{'node':'node-1', 'zone': 'us-east-1a'}, {'node':'node-2', 'zone': 'us-east-1b'}, {'node':'node-3', 'zone': 'us-east-1c'}]
        return  {'node_info': node_info, 'pod_count': 3, 'pods_per_node': 1}
    monkeypatch.setattr(evaluation, "get_pdb_allowed_disruptions", mock_get_pdb_allowed_disruptions)
    monkeypatch.setattr(evaluation, "get_deployment_node_summary", mock_get_deployment_node_summary)
    monkeypatch.setattr(evaluation, "find_matching_pdb", mock_find_matching_pdb)
    monkeypatch.setattr(evaluation, "get_deployment_pods_node_info", mock_get_deployment_pods_node_info)
    report = evaluation.node_upgrade_precheck(namespace, deployment)
    print("Upgrade precheck report: ", report)
    assert report['test-namespace']['Deployment_name'] == 'test-deployment'
    assert report['test-namespace']['Namespace'] == 'test-namespace'
    assert report['test-namespace']['Replicas'] == 3
    assert report['test-namespace']['Allowed_disruptions'] == 2
    assert report['test-namespace']['Blocking_PDB'] == 'test-pdb'
    assert report['test-namespace']['Node_info'] == [{'node': 'node-1', 'zone': 'us-east-1a'}, {'node': 'node-2', 'zone': 'us-east-1b'}, {'node': 'node-3', 'zone': 'us-east-1c'}]
    assert report['test-namespace']['Blocking_possible?'] == 'No'
    assert report['test-namespace']['Comments'] == 'The nodes where the pods are running will not block the upgrade'    