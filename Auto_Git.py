from git import Repo, GitCommandError
import os
import time
import shutil
import subprocess
from dotenv import load_dotenv
from github import Github, Auth, InputGitTreeElement
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AutoGit')

class AutoGitUp:
    """
    AutoGitUp 是一个自动将文件上传到 GitHub 的工具。
    
    参数:
    -----
    method: str
        上传文件到 GitHub 的方法。默认为 "LOCALCONFIG"。
        可用方法:
        - LOCALCONFIG: 使用本地 Git 配置上传文件
        - ENVCONFIG: 使用环境变量上传文件，包括 GITHUB_TOKEN, GITHUB_REPO, GITHUB_USERNAME
    """
    
    def __init__(self, method="LOCALCONFIG"):
        # 检查 Git 是否安装
        if not self._is_git_installed():
            raise FileNotFoundError("Git 未在系统中安装，请先安装 Git。")
        
        self.method = method
        self.token = None
        self.username = None
        self.repo_name = None
        self.repo = None
        self.github_api = None
        
        # 尝试初始化 Git 仓库
        self._ensure_repo_initialized()
        
        # 如果使用环境变量，则加载环境变量
        if self.method == "ENVCONFIG":
            self._load_env()
            self._init_github_api()
    
    def _is_git_installed(self):
        """检查系统中是否安装了 Git"""
        return shutil.which("git") is not None
    
    def _ensure_repo_initialized(self):
        """确保当前目录是一个 Git 仓库，如果不是则初始化"""
        try:
            self.repo = Repo(".")
            logger.info("找到现有 Git 仓库")
        except Exception:
            logger.info("未找到 Git 仓库，正在初始化...")
            self.repo = Repo.init(".")
            logger.info("Git 仓库初始化完成")
    
    def _load_env(self):
        """从环境变量加载配置"""
        load_dotenv()
        self.token = os.getenv('GITHUB_TOKEN')
        self.username = os.getenv('GITHUB_USERNAME')
        self.repo_name = os.getenv('GITHUB_REPO')
        
        if not all([self.token, self.username, self.repo_name]):
            raise ValueError("环境变量缺失。请确保设置了 GITHUB_TOKEN, GITHUB_USERNAME 和 GITHUB_REPO")
    
    def _init_github_api(self):
        """初始化 GitHub API 客户端"""
        try:
            self.github_api = Github(auth=Auth.Token(self.token))
            user = self.github_api.get_user()
            logger.info(f"已验证的用户: {user.login}")
        except Exception as e:
            raise ConnectionError(f"GitHub API 连接失败: {str(e)}")
    
    def get_changed_files(self):
        """
        获取已更改的文件列表并将它们添加到暂存区
        返回: 更改的文件列表
        """
        try:
            # 将所有更改添加到暂存区
            subprocess.run(['git', 'add', '.'], check=True, stdout=subprocess.PIPE)
            
            # 获取暂存区的文件
            result = subprocess.run(['git', 'diff', '--name-only', '--cached'], 
                                   check=True, stdout=subprocess.PIPE)
            
            changed_files = [f for f in result.stdout.decode('utf-8').split('\n') 
                            if f and not f.startswith('.')]
            
            return changed_files
        except subprocess.CalledProcessError as e:
            logger.error(f"获取更改的文件失败: {str(e)}")
            return []
    
    def _ensure_remote_exists(self):
        """确保远程仓库存在，如果不存在则提示用户添加"""
        if not self.repo.remotes:
            logger.warning("未找到远程仓库")
            remote_url = input("请输入远程仓库 URL (按 'q' 退出): ")
            if remote_url.lower() == "q":
                return False
            
            try:
                self.repo.create_remote('origin', remote_url)
                logger.info(f"成功添加远程仓库: {remote_url}")
            except GitCommandError as e:
                logger.error(f"添加远程仓库失败: {str(e)}")
                return False
        return True
    
    def _get_remote_branch(self):
        """获取要推送的远程分支"""
        try:
            # 如果只有一个远程仓库，默认使用 origin
            if len(self.repo.remotes) == 1:
                remote = self.repo.remotes[0]
                logger.info(f"使用远程仓库: {remote.name}")
            else:
                # 如果有多个远程仓库，让用户选择
                print("发现多个远程仓库:")
                for i, remote in enumerate(self.repo.remotes):
                    print(f"{i+1}. {remote.name}")
                
                choice = input("请选择远程仓库编号 (默认: 1): ")
                try:
                    idx = int(choice) - 1 if choice else 0
                    remote = self.repo.remotes[idx]
                except (ValueError, IndexError):
                    remote = self.repo.remotes[0]
                    logger.info(f"默认选择远程仓库: {remote.name}")
            
            # 检查当前分支
            try:
                current_branch = self.repo.active_branch.name
            except TypeError:
                # 如果处于分离头指针状态
                current_branch = "main"
                logger.warning("处于分离头指针状态，默认使用 main 分支")
            
            return remote, current_branch
        except Exception as e:
            logger.error(f"获取远程分支失败: {str(e)}")
            return None, None
    
    def _sync_with_remote(self, remote, branch):
        """同步远程仓库"""
        try:
            logger.info(f"正在从 {remote.name}/{branch} 同步代码...")
            remote.pull(branch)
            logger.info("同步完成")
            return True
        except GitCommandError as e:
            logger.error(f"同步失败: {str(e)}")
            return False
    
    def git_upload_by_localconfig(self, commit_message=None):
        """
        使用本地 Git 配置上传文件到 GitHub。
        """
        # 确保远程仓库存在
        if not self._ensure_remote_exists():
            return False
        
        # 获取更改的文件
        changed_files = self.get_changed_files()
        if not changed_files:
            logger.info("没有要上传的文件")
            return False
        
        logger.info(f"要上传的文件: {', '.join(changed_files)}")
        
        # 设置默认提交信息
        if not commit_message:
            commit_message = f"update files - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            # 提交更改
            commit = self.repo.index.commit(commit_message)
            logger.info(f"提交成功 - SHA: {commit.hexsha}")
            
            # 获取远程分支信息
            remote, branch = self._get_remote_branch()
            if not remote or not branch:
                return False
            
            # 推送到远程
            logger.info(f"正在推送到 {remote.name}/{branch}...")
            push_info = remote.push(f"{branch}:{branch}")
            
            # 检查推送结果
            if push_info and push_info[0].flags & push_info[0].ERROR:
                logger.error(f"推送失败: {push_info[0].summary}")
                return False
            
            logger.info("推送成功")
            
            # 输出提交详情
            logger.info("提交详情:")
            logger.info(f"  SHA: {commit.hexsha}")
            logger.info(f"  分支: {branch}")
            logger.info(f"  修改的文件: {', '.join(changed_files)}")
            
            # 等待 2 秒后同步远程仓库
            logger.info("等待 2 秒后同步远程仓库...")
            time.sleep(2)
            self._sync_with_remote(remote, branch)
            
            return True
        
        except GitCommandError as e:
            logger.error(f"Git 操作失败: {str(e)}")
            return False
    
    def git_upload_by_envconfig(self, commit_message=None):
        """
        使用环境变量上传文件到 GitHub。
        """
        # 设置默认提交信息
        if not commit_message:
            commit_message = f"update files - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            # 获取仓库
            github_repo = self.github_api.get_user().get_repo(self.repo_name)
            logger.info(f"仓库: {github_repo.full_name}")
            
            # 获取默认分支
            default_branch = github_repo.default_branch
            ref = github_repo.get_git_ref(f'heads/{default_branch}')
            
            # 获取当前提交和树
            current_commit = github_repo.get_commit(ref.object.sha)
            base_tree = current_commit.commit.tree
            logger.info(f"当前提交: {current_commit.sha}")
            
            # 获取更改的文件
            changed_files = self.get_changed_files()
            if not changed_files:
                logger.info("没有要上传的文件")
                return False
            
            logger.info(f"要上传的文件: {', '.join(changed_files)}")
            
            # 准备文件更新列表
            element_list = []
            for file_path in changed_files:
                try:
                    # 读取文件内容
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    # 处理文本和二进制文件
                    try:
                        # 尝试用 UTF-8 解码
                        content_str = content.decode('utf-8')
                        blob = github_repo.create_git_blob(content_str, 'utf-8')
                    except UnicodeDecodeError:
                        # 处理二进制文件
                        blob = github_repo.create_git_blob(content, 'base64')
                    
                    # 创建树元素
                    element = InputGitTreeElement(file_path, '100644', 'blob', blob.sha)
                    element_list.append(element)
                except FileNotFoundError:
                    logger.warning(f"文件未找到: {file_path}")
            
            # 创建新树
            tree = github_repo.create_git_tree(element_list, base_tree)
            new_commit = github_repo.create_git_commit(commit_message, tree, [current_commit])
            ref.edit(new_commit.sha)
            
            # 输出提交详情
            logger.info("提交详情:")
            logger.info(f"  SHA: {new_commit.sha}")
            logger.info(f"  分支: {default_branch}")
            logger.info(f"  修改的文件: {', '.join(changed_files)}")
            
            logger.info("文件上传成功")
            
            # 等待 2 秒后同步远程仓库
            logger.info("等待 2 秒后同步本地仓库...")
            time.sleep(2)
            #
            # 同步本地仓库
            remote = self.repo.remotes[0] if self.repo.remotes else None
            if remote:
                self._sync_with_remote(remote, default_branch)
            
            return True
        
        except Exception as e:
            logger.error(f"通过 API 上传文件失败: {str(e)}")
            return False
    
    def git_upload(self, commit_message=None):
        """
        使用指定的方法上传文件到 GitHub。
        返回: 成功时为 True，否则为 False
        """
        if self.method == "LOCALCONFIG":
            return self.git_upload_by_localconfig(commit_message)
        elif self.method == "ENVCONFIG":
            return self.git_upload_by_envconfig(commit_message)
        else:
            logger.error(f"无效的方法: {self.method}。可用方法: LOCALCONFIG, ENVCONFIG")
            return False


if __name__ == "__main__":
    try:
        # 创建 AutoGitUp 实例
        ag = AutoGitUp(method="LOCALCONFIG")
        
        # 提示用户输入提交信息或使用默认值
        user_message = input("请输入提交信息 (按回车使用默认值): ").strip()
        commit_message = user_message if user_message else None
        
        # 上传文件到 GitHub
        ag.git_upload(commit_message)
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")