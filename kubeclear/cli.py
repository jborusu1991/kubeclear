import sys
import csv
import argparse
from kubernetes import client, config
from kubernetes.client import ApiClient
from kubernetes.client.models.v1_deployment_list import V1DeploymentList
from .k8sclient import kubeclient
from .models import DeploymentModel
from . import evaluation
from typing import List,Dict
from tabulate import tabulate
from .evaluation import topology_spread_checks_report,namespace_checks_report

client = kubeclient()

def _build_parser() -> argparse.ArgumentParser:
 parser = argparse.ArgumentParser(
        prog="kubeclear",
        description=(
            "Tool to check a cluster for best practise before upgrade and also checks for HA of pods"
        ),
    )

 parser.add_argument(
        "--namespaces",
        "-n",
        nargs="+",
        metavar="NAMESPACES",
        help="provide list of namespaces to iterate and check for pods that are not following best practises",
    )

 parser.add_argument(
         "--upgrade-precheck",
         action="store_true",
         help="check for pods that might block the upgrade of nodes in the cluster",
     )

 parser.add_argument(
         "--topology-spread-check",
            action="store_true",
            help="check for pods that are not following topology spread best practises",
 )

 parser.add_argument(
         "--output",
         choices=["table", "csv"],
         default="table",
         help="report output format: table (default, printed to stdout) or csv (written to a file)",
     )

 parser.add_argument(
         "--output-file",
         default="kubeclear_report.csv",
         help="path to write the report to when --output csv is used (default: kubeclear_report.csv)",
     )
 return parser


def parse_deployments(namespaces:List[str]) -> Dict[str, V1DeploymentList]:
  apps_api = client.appsV1Api()
  api_client = ApiClient()
  models_namespace: Dict[str, List[DeploymentModel]] = {}
  for namespace in namespaces:
      deployments = apps_api.list_namespaced_deployment(
          namespace=namespace
      )
      models = []
      for deployment in deployments.items:
          deployment_dict = api_client.sanitize_for_serialization(deployment)
          deployment_dict['apiVersion'] = deployment_dict.get('apiVersion') or 'apps/v1'
          deployment_dict['kind'] = deployment_dict.get('kind') or 'Deployment'
          model = DeploymentModel.model_validate(
            deployment_dict
        )
          models.append(model)

      models_namespace[namespace] = models
  return models_namespace


def format_node_info(node_info_value) -> str:
  if isinstance(node_info_value, list):
    return ",".join([info['node']+'-'+info['zone'] for info in node_info_value])
  return node_info_value


      
 
def main(argv: List[str] = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  Headers_topology = ['Namespace','Deployment_name','Replicas','Node_info','Zone_violated','Hostname_violated','Voilated','Comments']
  Headers_upgrade = ['Namespace','Deployment_name','Replicas','Allowed_disruptions','Blocking_PDB','Node_info','Blocking_possible','Comments']
  report_topology=[]
  report_upgrade=[]

  if not args.namespaces:
    print("provide atleast one namespace")
    return 1

  models_namespace = parse_deployments(args.namespaces)

  if args.topology_spread_check:
     for namespace in models_namespace.keys():
       for model in models_namespace[namespace]:
         report_topology_temp = evaluation.check_topology_spread(namespace,model)
         Deployment_name = report_topology_temp[namespace]['Deployment_name']
         Replicas = report_topology_temp[namespace]['Replicas']
         Zone_violated = report_topology_temp[namespace]['Zone_violated']
         Hostname_violated = report_topology_temp[namespace]['Hostname_violated']
         Voilated = report_topology_temp[namespace]['Voilated?']
         Comments = report_topology_temp[namespace]['Comments']
         Node_info = format_node_info(report_topology_temp[namespace]['Node_info'])

         report_topology.append([namespace,Deployment_name,Replicas,Node_info,Zone_violated,Hostname_violated,Voilated,Comments])

  if args.upgrade_precheck:
    for namespace in models_namespace.keys():
      for model in models_namespace[namespace]:
        report_upgrade_temp = evaluation.node_upgrade_precheck(namespace,model)
        Deployment_name = report_upgrade_temp[namespace]['Deployment_name']
        Replicas = report_upgrade_temp[namespace]['Replicas']
        Allowed_disruptions = report_upgrade_temp[namespace]['Allowed_disruptions']
        Blocking_PDB = report_upgrade_temp[namespace]['Blocking_PDB']
        Comments = report_upgrade_temp[namespace]['Comments']
        Blocking_possible = report_upgrade_temp[namespace]['Blocking_possible?']
        Node_info = format_node_info(report_upgrade_temp[namespace]['Node_info'])

        report_upgrade.append([namespace,Deployment_name,Replicas,Allowed_disruptions,Blocking_PDB,Node_info,Blocking_possible,Comments])

  sections = []
  if args.topology_spread_check:
    sections.append(("Topology Spread Report", Headers_topology, report_topology))
  if args.upgrade_precheck:
    sections.append(("Upgrade Precheck Report", Headers_upgrade, report_upgrade))

  if args.output == "csv":
    with open(args.output_file, "w", newline="") as csv_file:
      writer = csv.writer(csv_file)
      for index, (title, headers, rows) in enumerate(sections):
        if index > 0:
          writer.writerow([])
        writer.writerow([f"----- {title} -----"])
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Report written to {args.output_file}")
  else:
    for index, (title, headers, rows) in enumerate(sections):
      if index > 0:
        print()
      print(f"----- {title} -----")
      print(tabulate(rows, headers=headers, tablefmt="grid"))



if __name__ == "__main__":
    sys.exit(main())