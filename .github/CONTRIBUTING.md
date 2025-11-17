# Contributing to Pixel Prompt

Thank you for your interest in contributing to Pixel Prompt! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Branch Protection Rules](#branch-protection-rules)
- [Pull Request Process](#pull-request-process)
- [Testing Requirements](#testing-requirements)
- [Code Style Guidelines](#code-style-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Security Considerations](#security-considerations)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors. Please:

- Be respectful and constructive in discussions
- Welcome newcomers and help them get started
- Focus on what is best for the community
- Show empathy towards other contributors

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Python 3.12+
- AWS CLI configured (for deployment)
- Git and GitHub account

### Setting Up Development Environment

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/pixel-prompt.git
   cd pixel-prompt
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/HatmanStack/pixel-prompt.git
   ```

4. **Install dependencies**:
   ```bash
   # Frontend
   cd frontend
   npm ci

   # Backend
   cd ../backend
   pip install -r requirements.txt
   pip install -r tests/requirements.txt
   ```

5. **Set up environment variables**:
   ```bash
   # Frontend
   cp frontend/.env.example frontend/.env
   # Edit .env with your local configuration

   # Backend
   cp backend/.env.example backend/.env
   # Edit .env with your API keys (for local testing)
   ```

See [DEVELOPMENT.md](../docs/DEVELOPMENT.md) for detailed setup instructions.

## Development Workflow

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Make your changes** following code style guidelines

4. **Run tests locally**:
   ```bash
   # Frontend
   cd frontend
   npm run lint
   npm test
   npm run build

   # Backend
   cd backend
   pytest tests/unit/ -v
   pytest tests/integration/ -v
   ```

5. **Commit your changes** using conventional commits:
   ```bash
   git add .
   git commit -m "feat(scope): add new feature"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request** on GitHub

## Branch Protection Rules

The `main` branch is protected with the following rules:

- ✅ **Required status checks**: All CI tests must pass before merging
  - `test-frontend` - Frontend tests and linting
  - `test-backend` - Backend tests
  - `npm-audit` - Frontend security scan
  - `bandit-scan` - Backend security scan

- ✅ **Required reviews**: At least 1 approval from a maintainer

- ✅ **Conversation resolution**: All comments must be resolved

- ❌ **Direct pushes blocked**: Changes must go through pull requests

- ❌ **Force pushes blocked**: Cannot rewrite history on main

### Why Branch Protection?

Branch protection ensures:
- Code quality through automated testing
- Security through vulnerability scanning
- Code review before merging
- Stable main branch for deployments

## Pull Request Process

1. **Use the PR template**: Fill out all sections of the PR template
2. **Link related issues**: Use "Closes #123" or "Related to #456"
3. **Add tests**: All new features require tests
4. **Update documentation**: Update README, API docs, or other docs as needed
5. **Wait for CI**: All checks must pass before review
6. **Address review comments**: Make requested changes and push updates
7. **Get approval**: At least 1 maintainer must approve
8. **Merge**: Maintainer will merge once approved

### PR Checklist

Before submitting a PR, ensure:

- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] No console.log or debug code
- [ ] Code follows style guidelines
- [ ] Commit messages follow conventional commits
- [ ] No merge conflicts with main
- [ ] Security considerations reviewed

## Testing Requirements

### Frontend Tests

- **Unit tests**: Test individual components
- **Integration tests**: Test user flows
- **Coverage target**: 60%+ for new features
- **Tools**: Vitest, React Testing Library

Example:
```javascript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

### Backend Tests

- **Unit tests**: Test functions and handlers
- **Integration tests**: Test API endpoints
- **Coverage target**: 70%+ for critical paths
- **Tools**: pytest, moto (for AWS mocking)

Example:
```python
def test_generate_endpoint(api_endpoint):
    response = requests.post(f"{api_endpoint}/generate", json={
        "prompt": "test",
        "ip": "1.2.3.4"
    })
    assert response.status_code == 200
    assert "jobId" in response.json()
```

### Running Tests

```bash
# Frontend
cd frontend
npm test                    # Run all tests
npm test -- MyComponent     # Run specific test
npm test -- --coverage      # With coverage

# Backend
cd backend
pytest tests/unit/ -v                # Unit tests
pytest tests/integration/ -v         # Integration tests
pytest tests/ -v --cov=src           # With coverage
```

## Code Style Guidelines

### Frontend (JavaScript/JSX)

- **ESLint**: Follow configured ESLint rules
- **Formatting**: Use Prettier (auto-format on save)
- **Naming**:
  - Components: PascalCase (`MyComponent.jsx`)
  - Functions: camelCase (`handleClick`)
  - Constants: UPPER_SNAKE_CASE (`API_ENDPOINT`)
- **File structure**: One component per file
- **Imports**: Group and order (React, third-party, local)

### Backend (Python)

- **PEP 8**: Follow Python style guide
- **Formatting**: Use Black (auto-format)
- **Type hints**: Use type annotations
- **Docstrings**: Document functions and classes
- **Naming**:
  - Functions: snake_case (`get_user_data`)
  - Classes: PascalCase (`JobManager`)
  - Constants: UPPER_SNAKE_CASE (`MAX_RETRIES`)

### General

- **Comments**: Explain "why", not "what"
- **DRY**: Don't repeat yourself
- **YAGNI**: You aren't gonna need it (avoid over-engineering)
- **Error handling**: Handle errors gracefully
- **Logging**: Use structured logging with correlation IDs

## Commit Message Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): brief description

[optional body]

[optional footer]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `perf`: Performance improvement
- `ci`: CI/CD changes
- `chore`: Maintenance tasks

### Examples

```bash
feat(frontend): add image export feature
fix(backend): resolve S3 retry race condition
docs(api): update API_INTEGRATION.md with new endpoint
test(frontend): add tests for ImageGrid component
ci: add security scanning workflow
perf(backend): optimize Lambda cold start time
```

### Scope

Use relevant scope:
- `frontend` - React frontend changes
- `backend` - Python backend changes
- `ci` - GitHub Actions workflows
- `docs` - Documentation
- Specific component/module names

## Security Considerations

### Never Commit Secrets

- API keys, passwords, credentials → Use `.env` files (gitignored)
- AWS credentials → Use GitHub Secrets
- Sensitive data → Always review before committing

### Security Best Practices

- Review dependencies for vulnerabilities
- Sanitize user inputs
- Follow AWS security best practices
- Use HTTPS for all external requests
- Implement proper error handling (don't leak sensitive info)

### Reporting Security Vulnerabilities

**DO NOT** open a public issue for security vulnerabilities.

Instead:
1. Email security reports to repository owner
2. Include description, steps to reproduce, impact
3. Allow time for fix before public disclosure

See [SECURITY.md](../SECURITY.md) for details.

## Documentation

Update documentation when:
- Adding new features → Update README, API docs
- Changing behavior → Update relevant docs
- Adding environment variables → Update `.env.example`
- Changing deployment → Update `docs/DEPLOYMENT.md`

## Questions or Issues?

- **Bugs**: Open an issue using the bug report template
- **Features**: Open an issue using the feature request template
- **Questions**: Open a discussion or issue
- **Help**: Tag issues with `help wanted` or `good first issue`

## Recognition

Contributors will be:
- Listed in project README
- Credited in release notes
- Mentioned in CHANGELOG.md

Thank you for contributing to Pixel Prompt! 🎨✨

---

**Maintainers**: See [CODEOWNERS](CODEOWNERS) file
**License**: Apache 2.0 - See [LICENSE](../LICENSE) file
