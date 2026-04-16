/**
 * AuthModal.tsx
 * 最终稳健版：修复了校验时序、字段污染风险，并保持 TS 类型严谨。
 */
import React, { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import {
  Alert,
  Button,
  Form,
  Input,
  message,
  Modal,
  Tabs,
  Typography,
} from 'antd'
import {
  GithubOutlined,
  LockOutlined,
  MailOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'

const { Text, Link } = Typography

interface UserInfo {
  id: number
  email: string
  username: string
  is_new?: boolean
  [key: string]: unknown
}

interface AuthModalProps {
  open: boolean
  onClose: () => void
  onSuccess: (user: UserInfo) => void
}

type AuthMode = 'password' | 'emailCode' | 'resetPassword'

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  timeout: 15000,
})

const AuthModal: React.FC<AuthModalProps> = ({ open, onClose, onSuccess }) => {
  const [mode, setMode] = useState<AuthMode>('password')
  const [pwdTab, setPwdTab] = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const [sendLoading, setSendLoading] = useState(false)
  const [githubLoading, setGithubLoading] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')

  const [pwdForm] = Form.useForm()
  const [codeForm] = Form.useForm()
  const [resetForm] = Form.useForm()

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!open) {
      setMode('password')
      setPwdTab('login')
      setErrorMsg('')
      setCountdown(0)
      setGithubLoading(false)
      pwdForm.resetFields()
      codeForm.resetFields()
      resetForm.resetFields()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [open, pwdForm, codeForm, resetForm])

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  const startCountdown = () => {
    setCountdown(60)
    timerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current)
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }

  const handleCatchError = (err: unknown) => {
    const msg = (err as { response?: { data?: { msg?: string } } })
      ?.response?.data?.msg || '网络错误，请稍后重试'
    setErrorMsg(msg)
  }

  // 【优化 1】先校验再取值，确保 email 数据的稳定性
  const handleSendCode = async (purpose: 'login' | 'reset_password') => {
    const currentForm = purpose === 'login' ? codeForm : resetForm
    try {
      // 显式校验 email 字段，直接从返回值中获取经过清洗的 email
      const values = await currentForm.validateFields(['email'])
      const email = (values.email || '').trim()

      setSendLoading(true)
      setErrorMsg('')

      const res = await api.post(
        '/auth/send-email-code',
        { email, purpose },
        { headers: { 'Content-Type': 'application/json' } }
      )

      if (res.data?.code === 200) {
        message.success('验证码已发送，请查收邮件 📧')
        startCountdown()
      } else {
        setErrorMsg(res.data?.msg || '发送失败')
      }
    } catch (err: unknown) {
      // 只有在非 Form 校验错误时才展示全局 Alert
      if (!(err as { errorFields?: unknown[] })?.errorFields) {
        handleCatchError(err)
      }
    } finally {
      setSendLoading(false)
    }
  }

  // 【优化 2】显式控制 Payload，杜绝脏字段风险
  const handlePasswordAuth = async () => {
    try {
      const values = await pwdForm.validateFields()
      // ✅ 注册时必须勾选同意协议
      if (pwdTab === 'register') {
        const box = document.getElementById('agree') as HTMLInputElement | null;
        if (!box?.checked) {
          message.warning('请先阅读并同意《用户协议》和《隐私政策》');
          return;
        }
      }

      setLoading(true)
      setErrorMsg('')

      const endpoint = pwdTab === 'login' ? '/auth/login' : '/auth/register'
      
      // 显式定义字段，防止 register 的 username 带入 login 请求
      const payload = pwdTab === 'login' 
        ? { email: values.email, password: values.password }
        : { email: values.email, password: values.password, username: values.username }

      const res = await api.post(endpoint, payload)
      if (res.data?.code === 200) {
        onSuccess(res.data.data)
        onClose()
        message.success(pwdTab === 'login' ? '登录成功 👋' : '注册成功 🎉')
      } else {
        setErrorMsg(res.data?.msg || '操作失败')
      }
    } catch (err: unknown) {
      if (!(err as { errorFields?: unknown[] })?.errorFields) {
        handleCatchError(err)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleEmailLogin = async () => {
    // ✅ 检查邮箱验证码登录的勾选框
    const box = document.getElementById('agree-code') as HTMLInputElement | null;
    if (!box?.checked) {
      message.warning('请先阅读并同意《用户协议》和《隐私政策》');
      return;
    }

    try {
      const values = await codeForm.validateFields()
      setLoading(true)
      setErrorMsg('')
      
      // 验证码登录通常只需 email 和 code
      const res = await api.post('/auth/email-login', {
        email: values.email,
        code: values.code
      })
      
      if (res.data?.code === 200) {
        onSuccess(res.data.data)
        onClose()
        message.success(res.data.data.is_new ? '注册并登录成功 🎉' : '登录成功 👋')
      } else {
        setErrorMsg(res.data?.msg || '登录失败')
      }
    } catch (err: unknown) {
      if (!(err as { errorFields?: unknown[] })?.errorFields) {
        handleCatchError(err)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleResetPassword = async () => {
    try {
      const values = await resetForm.validateFields()
      setLoading(true)
      setErrorMsg('')

      const res = await api.post('/auth/reset-password', {
        email: values.email,
        code: values.code,
        new_password: values.new_password,
        confirm_password: values.confirm_password,
      })

      if (res.data?.code === 200) {
        message.success('密码重置成功，请使用新密码登录 ✅')
        setMode('password')
        setPwdTab('login')
        pwdForm.setFieldValue('email', values.email)
        resetForm.resetFields()
        setCountdown(0)
        if (timerRef.current) clearInterval(timerRef.current)
      } else {
        setErrorMsg(res.data?.msg || '重置失败')
      }
    } catch (err: unknown) {
      if (!(err as { errorFields?: unknown[] })?.errorFields) {
        handleCatchError(err)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleGithubLogin = async () => {
    setGithubLoading(true)
    try {
      const res = await api.get('/auth/github/login')
      if (res.data?.code === 200 && res.data?.data?.auth_url) {
        window.open(res.data.data.auth_url, '_blank', 'width=720,height=760')
        onClose()
      } else {
        message.error(res.data?.msg || 'GitHub 登录暂未开放')
      }
    } catch {
      message.error('获取 GitHub 登录链接失败')
    } finally {
      setGithubLoading(false)
    }
  }

  // --- UI 部分保持不变，已应用之前的全部修复 ---
  const BottomLinks = () => (
    <div style={{ textAlign: 'center', marginTop: 12, fontSize: 13 }}>
      {mode !== 'password' && (
        <Link onClick={() => { setMode('password'); setErrorMsg('') }}> ← 返回密码登录 </Link>
      )}
      {mode === 'password' && (
        <>
          <Link onClick={() => { setMode('emailCode'); setErrorMsg('') }}> 验证码登录 </Link>
          <Text type="secondary" style={{ margin: '0 8px' }}>|</Text>
          <Link onClick={() => { setMode('resetPassword'); setErrorMsg('') }}> 忘记密码？ </Link>
        </>
      )}
    </div>
  )

  const renderContent = () => {
    if (mode === 'password') {
      return (
        <>
          <Tabs
            activeKey={pwdTab}
            onChange={k => { setPwdTab(k as 'login' | 'register'); setErrorMsg('') }}
            centered
            items={[{ key: 'login', label: '登录' }, { key: 'register', label: '注册' }]}
          />
          <Form form={pwdForm} layout="vertical" size="large" style={{ marginTop: 8 }}>
            {pwdTab === 'register' && (
              <Form.Item name="username" label="昵称（可选）">
                <Input prefix={<UserOutlined />} placeholder="不填则取邮箱前缀" maxLength={50} />
              </Form.Item>
            )}
            <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
              <Input prefix={<MailOutlined />} placeholder="请输入邮箱" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少6位' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" />
            </Form.Item>
          {/* ✅ 注册页合规勾选框 */}
          {pwdTab === 'register' && (
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 12 }}>
                <input
                type="checkbox"
                id="agree"
                style={{ marginTop: 4, cursor: 'pointer' }}
              />
              <label htmlFor="agree" style={{ fontSize: 12, lineHeight: 1.6, cursor: 'pointer' }}>
                我已阅读并同意
                <a href="/terms" target="_blank" rel="noreferrer" style={{ color: '#6366f1', margin: '0 2px' }}>《用户协议》</a>
                和
                <a href="/privacy" target="_blank" rel="noreferrer" style={{ color: '#6366f1', margin: '0 2px' }}>《隐私政策》</a>，
                了解本系统为 AI 情绪陪伴工具，不构成医疗诊断或心理治疗。
              </label>
            </div>
          )}

            {errorMsg && <Alert type="error" message={errorMsg} showIcon style={{ marginBottom: 12 }} />}
            <Button type="primary" block loading={loading} onClick={handlePasswordAuth}>
              {pwdTab === 'login' ? '登录' : '注册'}
            </Button>
          </Form>
        </>
      )
    }

    if (mode === 'emailCode') {
      return (
        <Form form={codeForm} layout="vertical" size="large">
          <div style={{ textAlign: 'center', marginBottom: 16 }}><Text strong style={{ fontSize: 16 }}>📧 邮箱验证码登录</Text></div>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
            <Input prefix={<MailOutlined />} placeholder="请输入邮箱" />
          </Form.Item>
                    {/* ✅ 邮箱验证码登录的勾选框 */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 12 }}>
            <input
              type="checkbox"
              id="agree-code"
              style={{ marginTop: 4, cursor: 'pointer' }}
            />
            <label htmlFor="agree-code" style={{ fontSize: 12, lineHeight: 1.6, cursor: 'pointer' }}>
              我已阅读并同意
              <a href="/terms" target="_blank" rel="noreferrer" style={{ color: '#6366f1', margin: '0 2px' }}>《用户协议》</a>和
              <a href="/privacy" target="_blank" rel="noreferrer" style={{ color: '#6366f1', margin: '0 2px' }}>《隐私政策》</a>。
              首次使用将自动创建账号。
            </label>
          </div>
          <Form.Item label="验证码" required>
            <div style={{ display: 'flex', gap: 8 }}>
              <Form.Item name="code" noStyle rules={[{ required: true, message: '请输入验证码' }, { len: 6, message: '验证码为6位' }]}>
                <Input prefix={<SafetyCertificateOutlined />} placeholder="6位数字" maxLength={6} />
              </Form.Item>
              <Button loading={sendLoading} disabled={countdown > 0} onClick={() => handleSendCode('login')} style={{ minWidth: 110 }}>
                {countdown > 0 ? `${countdown}s` : '发送验证码'}
              </Button>
            </div>
          </Form.Item>
          {errorMsg && <Alert type="error" message={errorMsg} showIcon style={{ marginBottom: 12 }} />}
          <Button type="primary" block loading={loading} onClick={handleEmailLogin}> 登录 / 注册 </Button>
        </Form>
      )
    }

    return (
      <Form form={resetForm} layout="vertical" size="large">
        <div style={{ textAlign: 'center', marginBottom: 16 }}><Text strong style={{ fontSize: 16 }}>🔑 找回密码</Text></div>
        <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
          <Input prefix={<MailOutlined />} placeholder="请输入已注册邮箱" />
        </Form.Item>
        <Form.Item label="验证码" required>
          <div style={{ display: 'flex', gap: 8 }}>
            <Form.Item name="code" noStyle rules={[{ required: true, message: '请输入验证码' }, { len: 6, message: '验证码为6位' }]}>
              <Input prefix={<SafetyCertificateOutlined />} placeholder="验证码" maxLength={6} />
            </Form.Item>
            <Button loading={sendLoading} disabled={countdown > 0} onClick={() => handleSendCode('reset_password')} style={{ minWidth: 110 }}>
              {countdown > 0 ? `${countdown}s` : '发送验证码'}
            </Button>
          </div>
        </Form.Item>
        <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '至少6位' }]}>
          <Input.Password prefix={<LockOutlined />} placeholder="新密码" />
        </Form.Item>
        <Form.Item name="confirm_password" label="确认新密码" dependencies={['new_password']}
          rules={[
            { required: true, message: '请再次输入新密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                return Promise.reject(new Error('两次密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder="请再次输入" />
        </Form.Item>
        {errorMsg && <Alert type="error" message={errorMsg} showIcon style={{ marginBottom: 12 }} />}
        <Button type="primary" block loading={loading} onClick={handleResetPassword}> 重置密码 </Button>
      </Form>
    )
  }

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={420} centered destroyOnHidden>
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div style={{ fontSize: 28 }}>🌸</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: '#4a3f6b' }}>媛心烨语</div>
      </div>
      {renderContent()}
      <BottomLinks />
      <div style={{ display: 'flex', alignItems: 'center', margin: '16px 0 12px' }}>
        <div style={{ flex: 1, height: 1, background: '#eee' }} /><Text type="secondary" style={{ margin: '0 12px', fontSize: 12 }}>其他方式</Text><div style={{ flex: 1, height: 1, background: '#eee' }} />
      </div>
      <Button block icon={<GithubOutlined />} loading={githubLoading} onClick={handleGithubLogin}> GitHub 授权登录 </Button>
    </Modal>
  )
}

export default AuthModal