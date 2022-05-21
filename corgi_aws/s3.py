import click
import os
import json
import logging
import boto3
from corgi_common.loggingutils import fatal, info
import tempfile


client = boto3.client('s3')

logger = logging.getLogger(__name__)

def _exists(bucket_name):
    try:
        meta_data = client.head_bucket(Bucket=bucket_name)
        logger.info(f"s3 bucket ({bucket_name}) meta data: {meta_data}")
        return True
    except Exception:
        logger.info(f"Bucket ({bucket_name}) doesn't exist")
        return False

def _force_delete(bucket_name):
    bucket = boto3.resource('s3').Bucket(bucket_name)
    bucket.objects.all().delete()
    bucket.delete()


@click.group(help="Utils for S3")
def s3():
    pass


@s3.command(help='Force delete bucket')
@click.option("--bucket-name", '-n')
def force_delete_bucket(bucket_name):
    _force_delete(bucket_name)


@s3.command(help="Create static web hosting bucket")
@click.option("--bucket-name", '-n')
@click.option("--domain-name", '-d', help='Will be the bucket name if specified')
@click.option("--force", '-f', is_flag=True, help='Delete bucket if exists')
def create_web_bucket(bucket_name, domain_name, force):
    bucket_name = domain_name or bucket_name
    if not bucket_name:
        fatal("No bucket specified.")
    if _exists(bucket_name):
        if force:
            info(f"Deleting bucket ({bucket_name}) forcibly ...")
            _force_delete(bucket_name)
        else:
            fatal(f'Bucket already exists. If you want to delete run: aws s3 rb --force s3://{bucket_name}')
    info(f"Creating bucket ({bucket_name}) ...")
    client.create_bucket(Bucket=bucket_name)
    tmp_html = tempfile.mktemp(suffix='.html')
    with open(tmp_html, 'w') as f:
        html = '''<!DOCTYPE html>
<html>
  <head>
    <title>Hello World!</title>
    <style>
        body {
            padding: 25px;
        }
        .title {
            color: #5C6AC4;
        }
    </style>

  </head>
  <body>
      <h1 class="title">S3 bucket (static web resource)</h1>
      <p id="currentTime"></p>
      <script>
          function showTime() {
              // document.getElementById('currentTime').innerHTML = new Date().toUTCString();
              document.getElementById('currentTime').innerHTML = new Date().toString();
          }
          showTime();
          setInterval(function () {
              showTime();
          }, 1000);
      </script>
  </body>
</html>
'''
        f.write(html)
    info("Uploading index.hmtl ...")
    client.upload_file(tmp_html, bucket_name, 'index.html', ExtraArgs={'ContentType': 'text/html'})
    bucket_policy = boto3.resource('s3').BucketPolicy(bucket_name)
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AddPerm",
                "Effect": "Allow",
                "Principal": "*",
                "Action": [
                    "s3:GetObject"
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}/*"
                ]
            }
        ]
    }
    info("Updating bucket policy ...")
    bucket_policy.put(Policy=json.dumps(policy))
    info("Configuring index page ...")
    # run_script(f'aws s3 website s3://{bucket_name} --index-document index.html', realtime=True)
    client.put_bucket_website(
        Bucket=bucket_name,
        WebsiteConfiguration={
            'IndexDocument': {
                'Suffix': 'index.html'
            }
        }
    )
    info(f"=> http://{bucket_name}.s3-website-{os.getenv('AWS_DEFAULT_REGION')}.amazonaws.com")
