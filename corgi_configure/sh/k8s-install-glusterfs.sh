set -e
kubectl wait --for=condition=ready --all node --timeout=180s

KEY=$key
KEY=${KEY:-Th15I5MyK3y}

TMP_DIR=$tmp_dir
TMP_DIR=${TMP_DIR:-/tmp}

if ! which python >/dev/null; then
    echo "No python found" >&2
    exit 1
fi


function git_sparse_clone() (
  rurl="$1" localdir="$2" && shift 2

  rm -rf "$localdir"
  mkdir -p "$localdir"
  cd "$localdir"

  git init
  git remote add -f origin "$rurl"

  git config core.sparseCheckout true

  # Loops over remaining args
  for i; do
    echo "$i" >> .git/info/sparse-checkout
  done

  git pull origin master
)

# REMOTE_DIR=/deploy
# git_sparse_clone "https://github.com/gluster/gluster-kubernetes.git" "$TMP_DIR" "$REMOTE_DIR"

REMOTE_DIR=/k8s/glusterfs_deploy
git_sparse_clone "https://github.com/ruanhao/python-for-fun.git" "$TMP_DIR" "$REMOTE_DIR"

cd $TMP_DIR/$REMOTE_DIR

cat <<EOF >topology.json
$topology
EOF

# kubectl delete service/deploy-heketi -n kube-system || true
# kubectl delete daemonset.apps/glusterfs -n kube-system || true
# kubectl delete serviceaccounts heketi-service-account -n kube-system || true
# kubectl delete secret heketi-config-secret -n kube-system || true
# kubectl delete clusterrolebinding heketi-sa-view || true
# sleep 3

# sed -i 's/--show-all//' gk-deploy
# sed -i 's|extensions/v1beta1|apps/v1|' kube-templates/glusterfs-daemonset.yaml
# sed -i 's|extensions/v1beta1|apps/v1|' kube-templates/deploy-heketi-deployment.yaml
# sed -i '12i \  selector:\
# \    matchLabels:\
# \      glusterfs: pod\
# \      glusterfs-node: pod' kube-templates/glusterfs-daemonset.yaml
bash gk-deploy -gvy -n kube-system --admin-key=$KEY --user-key=$KEY topology.json

cat <<EOF | kubectl create -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  namespace: kube-system
  name: my-gfs-storage
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: kubernetes.io/glusterfs
parameters:
  resturl: $(kubectl get svc/heketi -n kube-system --template 'http://{{.spec.clusterIP}}:{{(index .spec.ports 0).port}}')
  restuser: "admin"
  restuserkey: "$KEY"
reclaimPolicy: Delete
volumeBindingMode: Immediate
EOF