"""
Tests for packaging and deployment configuration.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


class TestPackaging:
    """Test packaging configuration."""
    
    def test_setup_py_exists(self):
        """Test that setup.py exists and is valid."""
        setup_path = Path("setup.py")
        assert setup_path.exists(), "setup.py file should exist"
        
        # Try to import setup.py to check for syntax errors
        import runpy
        try:
            runpy.run_path(str(setup_path), run_name="__main__")
        except SystemExit:
            # setup.py calls setup() which may cause SystemExit, this is expected
            pass
    
    def test_pyproject_toml_exists(self):
        """Test that pyproject.toml exists and is valid."""
        pyproject_path = Path("pyproject.toml")
        assert pyproject_path.exists(), "pyproject.toml file should exist"
        
        # Try to parse TOML
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                pytest.skip("No TOML parser available")
        
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)
        
        # Check required sections
        assert "build-system" in config
        assert "project" in config
        assert config["project"]["name"] == "chat-app"
        assert "version" in config["project"]
    
    def test_requirements_files_exist(self):
        """Test that requirements files exist."""
        assert Path("requirements.txt").exists()
        assert Path("requirements-optional.txt").exists()
    
    def test_requirements_format(self):
        """Test requirements file format."""
        with open("requirements.txt", "r") as f:
            content = f.read()
            # Should contain rich dependency
            assert "rich" in content.lower()
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        assert Path("Dockerfile").exists()
        assert Path("Dockerfile.server").exists()
        assert Path("Dockerfile.client").exists()
    
    def test_docker_compose_exists(self):
        """Test that docker-compose files exist."""
        assert Path("docker-compose.yml").exists()
        assert Path("docker-compose.dev.yml").exists()
    
    def test_dockerignore_exists(self):
        """Test that .dockerignore exists."""
        assert Path(".dockerignore").exists()


class TestConfiguration:
    """Test configuration files."""
    
    def test_config_examples_exist(self):
        """Test that configuration examples exist."""
        assert Path("config.example.json").exists()
        assert Path("config.example.yaml").exists()
    
    def test_environment_configs_exist(self):
        """Test that environment-specific configs exist."""
        assert Path("config/development.json").exists()
        assert Path("config/production.json").exists()
        assert Path("config/testing.json").exists()
    
    def test_config_json_format(self):
        """Test that JSON config files are valid."""
        config_files = [
            "config.example.json",
            "config/development.json",
            "config/production.json",
            "config/testing.json"
        ]
        
        for config_file in config_files:
            if Path(config_file).exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    assert "server" in config
                    assert "client" in config
                    assert "host" in config["server"]
                    assert "port" in config["server"]


class TestDocumentation:
    """Test documentation files."""
    
    def test_deployment_docs_exist(self):
        """Test that deployment documentation exists."""
        assert Path("DEPLOYMENT.md").exists()
        assert Path("CONFIGURATION.md").exists()
    
    def test_makefile_exists(self):
        """Test that Makefile exists."""
        assert Path("Makefile").exists()
    
    def test_deployment_doc_content(self):
        """Test deployment documentation content."""
        with open("DEPLOYMENT.md", "r") as f:
            content = f.read()
            # Should contain key sections
            assert "Installation" in content
            assert "Docker" in content
            assert "Configuration" in content
            assert "Environment Variables" in content


class TestDockerConfiguration:
    """Test Docker configuration."""
    
    def test_dockerfile_syntax(self):
        """Test Dockerfile syntax (basic check)."""
        dockerfiles = ["Dockerfile", "Dockerfile.server", "Dockerfile.client"]
        
        for dockerfile in dockerfiles:
            with open(dockerfile, "r") as f:
                content = f.read()
                # Should contain basic Docker instructions
                assert "FROM" in content
                assert "WORKDIR" in content
                assert "COPY" in content or "ADD" in content
    
    def test_docker_compose_syntax(self):
        """Test docker-compose file syntax."""
        compose_files = ["docker-compose.yml", "docker-compose.dev.yml"]
        
        for compose_file in compose_files:
            with open(compose_file, "r") as f:
                content = f.read()
                # Should contain basic compose structure
                assert "version:" in content
                assert "services:" in content
    
    def test_dockerignore_content(self):
        """Test .dockerignore content."""
        with open(".dockerignore", "r") as f:
            content = f.read()
            # Should ignore common files
            assert "__pycache__" in content
            assert ".git" in content
            assert "*.py[cod]" in content  # This covers *.pyc files


class TestMakefile:
    """Test Makefile configuration."""
    
    def test_makefile_targets(self):
        """Test that Makefile contains expected targets."""
        with open("Makefile", "r") as f:
            content = f.read()
            
            # Should contain common targets
            expected_targets = [
                "help", "install", "test", "clean", "build",
                "docker-build", "docker-run", "deploy-dev", "deploy-prod"
            ]
            
            for target in expected_targets:
                assert f"{target}:" in content, f"Target {target} should exist in Makefile"


class TestEntryPoints:
    """Test entry points and command-line interfaces."""
    
    def test_main_modules_exist(self):
        """Test that main modules exist."""
        assert Path("chat_app/server/main.py").exists()
        assert Path("chat_app/client/main.py").exists()
    
    def test_main_modules_have_main_function(self):
        """Test that main modules have main() function."""
        # This is a basic import test
        try:
            from chat_app.server import main as server_main
            from chat_app.client import main as client_main
            
            # Check that main functions exist
            assert hasattr(server_main, 'main')
            assert hasattr(client_main, 'main')
            assert callable(server_main.main)
            assert callable(client_main.main)
        except ImportError as e:
            pytest.fail(f"Failed to import main modules: {e}")


class TestPackageStructure:
    """Test package structure."""
    
    def test_package_init_files(self):
        """Test that __init__.py files exist."""
        package_dirs = [
            "chat_app",
            "chat_app/client",
            "chat_app/server", 
            "chat_app/shared",
            "chat_app/discovery"
        ]
        
        for package_dir in package_dirs:
            init_file = Path(package_dir) / "__init__.py"
            assert init_file.exists(), f"__init__.py should exist in {package_dir}"
    
    def test_test_structure(self):
        """Test test directory structure."""
        test_dirs = [
            "tests",
            "tests/unit",
            "tests/integration",
            "tests/fuzzing"
        ]
        
        for test_dir in test_dirs:
            assert Path(test_dir).exists(), f"Test directory {test_dir} should exist"
    
    def test_config_directory(self):
        """Test config directory structure."""
        assert Path("config").exists()
        assert Path("config").is_dir()


@pytest.mark.skipif(
    not Path("setup.py").exists(),
    reason="setup.py not found"
)
class TestSetupPyIntegration:
    """Test setup.py integration."""
    
    def test_setup_py_check(self):
        """Test setup.py check command."""
        try:
            result = subprocess.run(
                [sys.executable, "setup.py", "check"],
                capture_output=True,
                text=True,
                timeout=30
            )
            # setup.py check should not fail
            assert result.returncode == 0, f"setup.py check failed: {result.stderr}"
        except subprocess.TimeoutExpired:
            pytest.fail("setup.py check timed out")
        except FileNotFoundError:
            pytest.skip("Python not found in PATH")


class TestEnvironmentFiles:
    """Test environment configuration files."""
    
    def test_env_example_creation(self):
        """Test that we can create environment example."""
        # This would be created by make env-example
        env_vars = [
            "CHAT_SERVER_HOST",
            "CHAT_SERVER_PORT", 
            "CHAT_LOG_LEVEL",
            "CHAT_LOG_FILE"
        ]
        
        # Just verify the variables are documented somewhere
        with open("DEPLOYMENT.md", "r") as f:
            content = f.read()
            for var in env_vars:
                assert var in content, f"Environment variable {var} should be documented"